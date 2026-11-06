"""Async Gmail: AsyncGmail, the async counterpart of ``Gmail``.

Covers reading (messages, threads, labels, drafts), sending (send, reply,
forward, drafts) and organizing (labels, batch_modify, modify_message, trash,
filters). Requests go through ``gsuite_core.aio``, so retries, rate limits
and errors are the suite's; message parsing and MIME building are the sync
client's own code.

Messages and attachments returned here are not linked to a sync client: their
fluent methods (``message.trash()``, ``attachment.download()``) raise, pointing
to the AsyncGmail method to await instead.

Example:
    async with AsyncGmail(auth) as gmail:
        for message in await gmail.get_unread():
            print(message.subject)
        await gmail.batch_modify([m.id for m in unread], remove_labels=["UNREAD"])

Requires ``pip install "gsuite-sdk[async]"``.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
from collections.abc import AsyncIterator, Awaitable, Sequence
from typing import Any, NoReturn, TypeVar

from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.exceptions import GSuiteError, NotFoundError, SyncTokenExpiredError
from gsuite_gmail._labels import LabelResolver, is_system_label
from gsuite_gmail._mime import (
    MessageSpec,
    OutgoingAttachment,
    build_message,
    encode_for_api,
    forward_text,
    prefixed,
    reply_recipients,
    with_signature,
)
from gsuite_gmail._requests import (
    HISTORY_PAGE_SIZE,
    HistoryType,
    MessageFormat,
    add_history_page,
    finish_history,
    get_params,
    history_params,
    list_params,
)
from gsuite_gmail.client import BATCH_MODIFY_LIMIT, BATCH_SIZE
from gsuite_gmail.draft import Draft
from gsuite_gmail.history import HistoryDelta, IdPage
from gsuite_gmail.label import Label
from gsuite_gmail.message import Message
from gsuite_gmail.parser import GmailParser
from gsuite_gmail.query import Query
from gsuite_gmail.thread import Thread

API = "https://gmail.googleapis.com/gmail/v1/users"
T = TypeVar("T")


class _AsyncOnly:
    """Stands in for the sync client on messages from AsyncGmail.

    The fluent methods of Message and Attachment call the sync client; without
    this they would silently do nothing.
    """

    def __getattr__(self, name: str) -> NoReturn:
        raise TypeError(
            "This message came from AsyncGmail, whose messages have no sync client: "
            "await gmail.modify_message(...), gmail.trash(...), "
            "gmail.download_attachment(...) instead"
        )


_ASYNC_ONLY: Any = _AsyncOnly()


class AsyncGmail:
    """Async Gmail client.

    Args:
        auth: GoogleAuth (OAuth or service account) or google-auth credentials
        user_id: Gmail user ID ("me" for the authenticated user)
        concurrency: Requests in flight at once when fetching many messages,
            threads, labels or drafts (the sync client uses HTTP batches)
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT)
        transport: httpx transport (tests)
    """

    def __init__(
        self,
        auth: Any,
        user_id: str = "me",
        *,
        concurrency: int = 10,
        timeout: float | None = None,
        transport: Any = None,
    ) -> None:
        self._http = AsyncGoogleClient(auth, timeout=timeout, transport=transport)
        self.user_id = user_id
        self._base = f"{API}/{user_id}"
        self._semaphore = asyncio.Semaphore(concurrency)
        self._labels: LabelResolver | None = None
        self._email: str | None = None

    async def __aenter__(self) -> AsyncGmail:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    # ---- plumbing ----

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        kwargs.setdefault("service", "gmail")
        return await self._http.json(method, f"{self._base}/{path}", **kwargs)

    async def _gather(self, calls: Sequence[Awaitable[T]]) -> list[T | None]:
        """Run calls with bounded concurrency; one gone meanwhile (404) gives None."""

        async def bounded(call: Awaitable[T]) -> T | None:
            async with self._semaphore:
                try:
                    return await call
                except NotFoundError:
                    return None

        return list(await asyncio.gather(*(bounded(call) for call in calls)))

    @staticmethod
    def _link(message: Message) -> Message:
        attachments = [dataclasses.replace(a, _gmail=_ASYNC_ONLY) for a in message.attachments]
        return dataclasses.replace(message, _gmail=_ASYNC_ONLY, attachments=attachments)

    def _parse(self, data: dict[str, Any], include_body: bool = True) -> Message:
        return self._link(GmailParser.parse_message(data, include_body))

    async def _fetch_message(self, message_id: str, include_body: bool = True) -> Message:
        data = await self._json(
            "GET",
            f"messages/{message_id}",
            params={"format": "full" if include_body else "metadata"},
            resource_type="message",
            resource_id=message_id,
        )
        return self._parse(data, include_body)

    # ---- messages ----

    async def iter_messages(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
        include_body: bool = True,
    ) -> AsyncIterator[Message]:
        """Lazily yield messages matching criteria, following result pages.

        Each page's messages are fetched concurrently; one deleted while
        listing is skipped.
        """
        params: dict[str, Any] = {}
        if query:
            params["q"] = str(query)
        if labels:
            params["labelIds"] = labels
        page: list[str] = []
        async for ref in self._http.paginate(
            f"{self._base}/messages",
            "messages",
            service="gmail",
            params=params,
            max_items=max_results,
            max_page_size=500,
        ):
            page.append(ref["id"])
            if len(page) == BATCH_SIZE:
                for message in await self._fetch_many(page, include_body):
                    yield message
                page = []
        for message in await self._fetch_many(page, include_body):
            yield message

    async def _fetch_many(self, ids: list[str], include_body: bool) -> list[Message]:
        found = await self._gather([self._fetch_message(mid, include_body) for mid in ids])
        return [message for message in found if message is not None]

    async def get_messages(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
        include_body: bool = True,
    ) -> list[Message]:
        """Messages matching criteria (None = all matches; can be slow)."""
        return [m async for m in self.iter_messages(query, labels, max_results, include_body)]

    async def search(self, query: str | Query, max_results: int = 25) -> list[Message]:
        """Messages matching a Gmail query."""
        return await self.get_messages(query=query, max_results=max_results)

    async def get_unread(self, max_results: int = 25) -> list[Message]:
        """Unread messages."""
        return await self.get_messages(query="is:unread", max_results=max_results)

    async def get_starred(self, max_results: int = 25) -> list[Message]:
        """Starred messages."""
        return await self.get_messages(query="is:starred", max_results=max_results)

    async def get_important(self, max_results: int = 25) -> list[Message]:
        """Important messages."""
        return await self.get_messages(query="is:important", max_results=max_results)

    async def get_sent(self, max_results: int = 25) -> list[Message]:
        """Sent messages."""
        return await self.get_messages(query="in:sent", max_results=max_results)

    async def get_message(
        self,
        message_id: str,
        format: MessageFormat = "full",
        headers: Sequence[str] | None = None,
    ) -> Message | None:
        """A message by ID, or None if it doesn't exist (format/headers as in ``Gmail``)."""
        try:
            data = await self._json(
                "GET",
                f"messages/{message_id}",
                params=get_params(format, headers),
                resource_type="message",
                resource_id=message_id,
            )
        except NotFoundError:
            return None
        return self._parse(data, include_body=format == "full")

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Content of an attachment (``attachment.download()`` for sync messages)."""
        data = await self._json(
            "GET",
            f"messages/{message_id}/attachments/{attachment_id}",
            resource_type="attachment",
            resource_id=attachment_id,
        )
        return base64.urlsafe_b64decode(data.get("data", ""))

    async def trash(self, message_id: str) -> None:
        """Move a message to the trash."""
        await self._json(
            "POST", f"messages/{message_id}/trash", resource_type="message", resource_id=message_id
        )

    async def untrash(self, message_id: str) -> None:
        """Take a message out of the trash."""
        await self._json(
            "POST",
            f"messages/{message_id}/untrash",
            resource_type="message",
            resource_id=message_id,
        )

    # ---- threads ----

    def _parse_thread(self, data: dict[str, Any], include_body: bool = True) -> Thread:
        return Thread(
            id=data["id"],
            messages=[self._parse(m, include_body) for m in data.get("messages", [])],
            snippet=data.get("snippet", ""),
            raw=data,
        )

    async def _fetch_thread(
        self,
        thread_id: str,
        format: MessageFormat = "full",
        headers: Sequence[str] | None = None,
    ) -> Thread:
        data = await self._json(
            "GET",
            f"threads/{thread_id}",
            params=get_params(format, headers),
            resource_type="thread",
            resource_id=thread_id,
        )
        return self._parse_thread(data, include_body=format == "full")

    async def get_thread(
        self,
        thread_id: str,
        format: MessageFormat = "full",
        headers: Sequence[str] | None = None,
    ) -> Thread | None:
        """A conversation, or None if it doesn't exist (format/headers as in ``Gmail``)."""
        try:
            return await self._fetch_thread(thread_id, format, headers)
        except NotFoundError:
            return None

    async def get_threads(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
    ) -> list[Thread]:
        """Conversations matching criteria."""
        params: dict[str, Any] = {}
        if query:
            params["q"] = str(query)
        if labels:
            params["labelIds"] = labels
        ids = [
            ref["id"]
            async for ref in self._http.paginate(
                f"{self._base}/threads",
                "threads",
                service="gmail",
                params=params,
                max_items=max_results,
                max_page_size=500,
            )
        ]
        found = await self._gather([self._fetch_thread(tid) for tid in ids])
        return [thread for thread in found if thread is not None]

    # ---- labels ----

    async def _label_refs(self) -> list[dict[str, Any]]:
        response = await self._json("GET", "labels")
        refs: list[dict[str, Any]] = response.get("labels", [])
        return refs

    async def _resolver(self, names: Sequence[str]) -> LabelResolver:
        """A resolver for ``names``, listing the labels only if one isn't a system label."""
        if self._labels is not None:
            return self._labels
        if all(is_system_label(name) for name in names):
            return LabelResolver(list)
        refs = await self._label_refs()
        self._labels = LabelResolver(lambda: refs)
        return self._labels

    async def _label_ids(self, names: Sequence[str]) -> list[str]:
        """IDs for label names or IDs; ValidationError for an unknown one."""
        return (await self._resolver(names)).require(names)

    async def get_labels(self) -> list[Label]:
        """All labels, with message and thread counts."""
        refs = await self._label_refs()
        found = await self._gather(
            [self._json("GET", f"labels/{ref['id']}", resource_type="label") for ref in refs]
        )
        return [GmailParser.parse_label(data) for data in found if data is not None]

    async def create_label(
        self,
        name: str,
        show_in_label_list: bool = True,
        show_in_message_list: bool = True,
    ) -> Label:
        """Create a label. Use "Parent/Child" to nest it."""
        created = await self._json(
            "POST",
            "labels",
            json={
                "name": name,
                "labelListVisibility": "labelShow" if show_in_label_list else "labelHide",
                "messageListVisibility": "show" if show_in_message_list else "hide",
            },
            resource_type="label",
        )
        self._labels = None
        return GmailParser.parse_label(created)

    async def rename_label(self, label: str, new_name: str) -> Label:
        """Rename a label (by name or ID)."""
        (label_id,) = await self._label_ids([label])
        updated = await self._json(
            "PATCH",
            f"labels/{label_id}",
            json={"name": new_name},
            resource_type="label",
            resource_id=label_id,
        )
        self._labels = None
        return GmailParser.parse_label(updated)

    async def delete_label(self, label: str) -> bool:
        """Delete a label (by name or ID); False if there is no such label."""
        label_id = (await self._resolver([label])).resolve(label)
        if label_id is None:
            return False
        try:
            await self._json(
                "DELETE", f"labels/{label_id}", resource_type="label", resource_id=label_id
            )
        except NotFoundError:
            return False
        finally:
            self._labels = None
        return True

    async def batch_modify(
        self,
        message_ids: Sequence[str],
        add_labels: Sequence[str] | None = None,
        remove_labels: Sequence[str] | None = None,
    ) -> int:
        """Add/remove labels on many messages in a few calls (1000 per call).

        Labels can be names or IDs ("UNREAD", "STARRED", "INBOX", "Work").
        Example: remove_labels=["UNREAD"] marks read.

        Returns:
            Number of message IDs sent
        """
        add_ids = await self._label_ids(add_labels or [])
        remove_ids = await self._label_ids(remove_labels or [])
        if not add_ids and not remove_ids:
            return 0
        ids = list(message_ids)
        for start in range(0, len(ids), BATCH_MODIFY_LIMIT):
            body: dict[str, Any] = {"ids": ids[start : start + BATCH_MODIFY_LIMIT]}
            if add_ids:
                body["addLabelIds"] = add_ids
            if remove_ids:
                body["removeLabelIds"] = remove_ids
            await self._json("POST", "messages/batchModify", json=body)
        return len(ids)

    async def modify_message(
        self,
        message: Message,
        add_labels: Sequence[str] = (),
        remove_labels: Sequence[str] = (),
    ) -> Message:
        """Add/remove labels on one message, as the sync fluent methods do.

        Labels are names or IDs. Like ``message.add_label()``, an unknown name
        is skipped, and a label the message already has (or lacks) isn't sent.
        ``message.labels`` is updated; the same message is returned.

        Example:
            await gmail.modify_message(message, remove_labels=["UNREAD"])  # read
        """
        resolver = await self._resolver([*add_labels, *remove_labels])
        resolved_add = [resolver.resolve(name) for name in add_labels]
        resolved_remove = [resolver.resolve(name) for name in remove_labels]
        add = [i for i in dict.fromkeys(resolved_add) if i and i not in message.labels]
        remove = [i for i in dict.fromkeys(resolved_remove) if i and i in message.labels]
        if not add and not remove:
            return message
        body: dict[str, Any] = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        await self._json(
            "POST",
            f"messages/{message.id}/modify",
            json=body,
            resource_type="message",
            resource_id=message.id,
        )
        message.labels = [label for label in message.labels if label not in remove] + add
        return message

    # ---- filters ----

    async def list_filters(self) -> list[dict[str, Any]]:
        """Filters ({id, criteria, action} dicts as the API returns them)."""
        response = await self._json("GET", "settings/filters")
        filters: list[dict[str, Any]] = response.get("filter", [])
        return filters

    async def create_filter(
        self, criteria: dict[str, Any], action: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a filter; label names in the action are resolved to IDs."""
        action = dict(action)
        for key in ("addLabelIds", "removeLabelIds"):
            if key in action:
                action[key] = await self._label_ids(action[key])
        created: dict[str, Any] = await self._json(
            "POST",
            "settings/filters",
            json={"criteria": criteria, "action": action},
            resource_type="filter",
        )
        return created

    async def delete_filter(self, filter_id: str) -> bool:
        """Delete a filter; False if it doesn't exist."""
        try:
            await self._json(
                "DELETE",
                f"settings/filters/{filter_id}",
                resource_type="filter",
                resource_id=filter_id,
            )
        except NotFoundError:
            return False
        return True

    # ---- profile and signature ----

    # ---- incremental sync ----

    async def _iter_ids(
        self, kind: str, query: str | Query | None, labels: list[str] | None, limit: int | None
    ) -> AsyncIterator[str]:
        async for ref in self._http.paginate(
            f"{self._base}/{kind}",
            kind,
            service="gmail",
            params=list_params(query, labels),
            max_items=limit,
            max_page_size=500,
        ):
            yield ref["id"]

    def iter_message_ids(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = None,
    ) -> AsyncIterator[str]:
        """IDs of the matching messages, without fetching them (500 per request)."""
        return self._iter_ids("messages", query, labels, max_results)

    async def list_message_ids(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        page_token: str | None = None,
        page_size: int = 500,
    ) -> IdPage:
        """One page of matching message IDs and the next page's token (see ``Gmail``)."""
        params = {"maxResults": max(1, min(page_size, 500)), **list_params(query, labels)}
        if page_token:
            params["pageToken"] = page_token
        data = await self._json("GET", "messages", params=params)
        return IdPage(
            ids=[ref["id"] for ref in data.get("messages", [])],
            next_page_token=data.get("nextPageToken"),
        )

    def iter_thread_ids(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = None,
    ) -> AsyncIterator[str]:
        """IDs of the matching threads, without fetching them."""
        return self._iter_ids("threads", query, labels, max_results)

    async def get_history_id(self) -> str:
        """The mailbox's current history ID: where a first ``history`` call starts."""
        return str((await self.get_profile())["historyId"])

    async def history(
        self,
        start_history_id: str,
        history_types: Sequence[HistoryType] | None = None,
        label_id: str | None = None,
    ) -> HistoryDelta:
        """Message IDs added, deleted or relabeled since ``start_history_id`` (see ``Gmail``).

        Raises:
            SyncTokenExpiredError: Gmail no longer has that history; start over.
        """
        params = history_params(start_history_id, history_types, label_id)
        params["maxResults"] = HISTORY_PAGE_SIZE
        delta = HistoryDelta()
        while True:
            try:
                page = await self._json("GET", "history", params=params, resource_type="history")
            except NotFoundError as exc:
                raise SyncTokenExpiredError("gmail") from exc
            add_history_page(delta, page)
            if not page.get("nextPageToken"):
                return finish_history(delta)
            params["pageToken"] = page["nextPageToken"]

    async def get_profile(self) -> dict[str, Any]:
        """The authenticated user's profile."""
        profile: dict[str, Any] = await self._json("GET", "profile")
        return profile

    async def get_email(self) -> str:
        """The authenticated user's address (fetched once)."""
        if self._email is None:
            self._email = (await self.get_profile()).get("emailAddress", "")
        return self._email

    async def get_signature(self, send_as_email: str | None = None) -> str | None:
        """The account's HTML signature, or None (best effort, never raises)."""
        try:
            email = send_as_email or await self.get_email()
            settings = await self._json(
                "GET", f"settings/sendAs/{email}", resource_type="signature"
            )
        except GSuiteError:
            return None
        signature: str | None = settings.get("signature")
        return signature

    # ---- sending ----

    async def _compose(
        self,
        spec: MessageSpec,
        signature: bool = False,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """The API body for ``spec``, with the signature and threading headers added."""
        changes: dict[str, Any] = {}
        if signature and (sig := await self.get_signature()):
            changes["body"] = with_signature(spec.body, sig, spec.html)
        if reply_to:
            original = await self._fetch_message(reply_to, include_body=False)
            changes["in_reply_to"] = original.rfc822_message_id
            changes["references"] = original.references
            thread_id = thread_id or original.thread_id
        if changes:
            spec = dataclasses.replace(spec, **changes)
        return encode_for_api(build_message(spec), thread_id)

    async def _send(self, api_body: dict[str, Any]) -> Message:
        sent = await self._json("POST", "messages/send", json=api_body)
        return await self._fetch_message(sent["id"])

    async def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        signature: bool = False,
        reply_to: str | None = None,
        thread_id: str | None = None,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> Message:
        """Send an email (same arguments as ``Gmail.send``); returns the sent message."""
        spec = MessageSpec(to, subject, body, cc, bcc, html, attachments)
        return await self._send(await self._compose(spec, signature, reply_to, thread_id))

    async def reply(
        self,
        message: Message,
        body: str,
        html: bool = False,
        signature: bool = False,
        reply_all: bool = False,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> Message:
        """Reply in the message's thread (same rules as ``Gmail.reply``)."""
        to, cc = reply_recipients(message, await self.get_email(), reply_all)
        spec = MessageSpec(
            to, prefixed(message.subject, "Re:"), body, cc or None, None, html, attachments
        )
        return await self._send(
            await self._compose(spec, signature, reply_to=message.id, thread_id=message.thread_id)
        )

    async def forward(
        self,
        message: Message,
        to: list[str],
        body: str = "",
        include_attachments: bool = True,
    ) -> Message:
        """Forward a message, quoting it below ``body``."""
        attachments: list[OutgoingAttachment] = []
        if include_attachments:
            for attachment in message.attachments:
                content = (
                    attachment.download()
                    if attachment.is_inline
                    else await self.download_attachment(message.id, attachment.id)
                )
                attachments.append((attachment.filename, content))
        spec = MessageSpec(
            to,
            prefixed(message.subject, "Fwd:"),
            forward_text(message, body),
            attachments=attachments or None,
        )
        return await self._send(await self._compose(spec))

    # ---- drafts ----

    async def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        attachments: list[OutgoingAttachment] | None = None,
        reply_to: str | None = None,
    ) -> Draft:
        """Save a draft (same arguments as send())."""
        spec = MessageSpec(to, subject, body, cc, bcc, html, attachments)
        api_body = await self._compose(spec, reply_to=reply_to)
        created = await self._json(
            "POST", "drafts", json={"message": api_body}, resource_type="draft"
        )
        message = await self._fetch_message(created["message"]["id"])
        return Draft(id=created["id"], message=message)

    async def _fetch_draft(self, draft_id: str) -> Draft:
        data = await self._json(
            "GET",
            f"drafts/{draft_id}",
            params={"format": "full"},
            resource_type="draft",
            resource_id=draft_id,
        )
        return Draft(id=data["id"], message=self._parse(data["message"]))

    async def get_draft(self, draft_id: str) -> Draft | None:
        """A draft, or None if it doesn't exist."""
        try:
            return await self._fetch_draft(draft_id)
        except NotFoundError:
            return None

    async def list_drafts(self, max_results: int | None = 25) -> list[Draft]:
        """Drafts with their content (fetched concurrently)."""
        ids = [
            ref["id"]
            async for ref in self._http.paginate(
                f"{self._base}/drafts",
                "drafts",
                service="gmail",
                max_items=max_results,
                max_page_size=500,
            )
        ]
        found = await self._gather([self._fetch_draft(did) for did in ids])
        return [draft for draft in found if draft is not None]

    async def send_draft(self, draft_id: str) -> Message:
        """Send a draft; returns the sent message."""
        sent = await self._json(
            "POST",
            "drafts/send",
            json={"id": draft_id},
            resource_type="draft",
            resource_id=draft_id,
        )
        return await self._fetch_message(sent["id"])

    async def delete_draft(self, draft_id: str) -> bool:
        """Discard a draft; False if it doesn't exist."""
        try:
            await self._json(
                "DELETE", f"drafts/{draft_id}", resource_type="draft", resource_id=draft_id
            )
        except NotFoundError:
            return False
        return True
