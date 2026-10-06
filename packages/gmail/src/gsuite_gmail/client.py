"""Gmail client - high-level interface."""

import base64
import html as html_lib
import logging
import mimetypes
import os
import re
from collections.abc import Iterator, Sequence
from email.message import EmailMessage
from email.utils import parseaddr
from itertools import islice
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute, execute_batch, paginate
from gsuite_core.exceptions import GSuiteError, NotFoundError, ValidationError
from gsuite_gmail.draft import Draft
from gsuite_gmail.label import Label
from gsuite_gmail.message import Message
from gsuite_gmail.parser import GmailParser
from gsuite_gmail.query import Query
from gsuite_gmail.thread import Thread

logger = logging.getLogger(__name__)

# A file path, or (filename, content) for data already in memory
OutgoingAttachment = str | os.PathLike[str] | tuple[str, bytes]

# Gmail recommends at most 50 requests per HTTP batch
BATCH_SIZE = 50
# users.messages.batchModify accepts up to 1000 IDs per call
BATCH_MODIFY_LIMIT = 1000

# Fixed IDs that work without looking them up
SYSTEM_LABELS = frozenset(
    {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH", "CHAT"}
)


def _html_to_text(markup: str) -> str:
    """Rough plain-text version of HTML, for the text/plain alternative."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html_lib.unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()


def _prefixed(subject: str, prefix: str) -> str:
    """'Re: x' stays as is (any case); otherwise add the prefix."""
    return subject if subject.lower().startswith(prefix.lower()) else f"{prefix} {subject}"


class Gmail:
    """
    High-level Gmail client.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        gmail = Gmail(auth)

        # Get unread
        for msg in gmail.get_unread():
            print(msg.subject)
            msg.mark_as_read()

        # Send
        gmail.send(
            to=["user@example.com"],
            subject="Hello",
            body="World",
        )
    """

    def __init__(self, auth: GoogleAuth, user_id: str = "me"):
        """
        Initialize Gmail client.

        Args:
            auth: GoogleAuth instance with valid credentials
            user_id: Gmail user ID ("me" for authenticated user)
        """
        self.auth = auth
        self.user_id = user_id
        self._service: Any = None
        self._labels_cache: dict[str, str] | None = None
        self._email: str | None = None

    @property
    def service(self) -> Any:
        """Lazy-load Gmail API service."""
        if self._service is None:
            self._service = build(
                "gmail", "v1", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._service

    # ========== Message retrieval ==========

    def iter_messages(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
        include_body: bool = True,
    ) -> Iterator[Message]:
        """
        Lazily yield messages matching criteria, following result pages.

        Messages are fetched in HTTP batches of 50 rather than one request
        each. A message deleted while listing is skipped.

        Args:
            query: Gmail search query (str or Query object)
            labels: Filter by label IDs
            max_results: Maximum messages to yield (None = all matches)
            include_body: Whether to fetch full message content
        """
        params: dict[str, Any] = {"userId": self.user_id}
        if query:
            params["q"] = str(query)
        if labels:
            params["labelIds"] = labels

        refs = paginate(
            self.service.users().messages().list,
            "messages",
            "gmail",
            max_items=max_results,
            max_page_size=500,
            **params,
        )
        while chunk := [ref["id"] for ref in islice(refs, BATCH_SIZE)]:
            yield from self._fetch_messages(chunk, include_body)

    def get_messages(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
        include_body: bool = True,
    ) -> list[Message]:
        """
        Get messages matching criteria.

        Args:
            query: Gmail search query (str or Query object)
            labels: Filter by label IDs
            max_results: Maximum messages to return (None = all matches; can be slow)
            include_body: Whether to fetch full message content

        Returns:
            List of Message objects
        """
        return list(self.iter_messages(query, labels, max_results, include_body))

    def _fetch_messages(self, message_ids: list[str], include_body: bool) -> list[Message]:
        requests = [
            self.service.users()
            .messages()
            .get(userId=self.user_id, id=mid, format="full" if include_body else "metadata")
            for mid in message_ids
        ]
        messages = []
        for result in execute_batch(self.service, requests, "gmail", "message", BATCH_SIZE):
            if isinstance(result, NotFoundError):
                continue  # deleted between listing and fetching
            if isinstance(result, Exception):
                raise result
            messages.append(self._parse_message(result, include_body))
        return messages

    def search(
        self,
        query: str | Query,
        max_results: int = 25,
    ) -> list[Message]:
        """
        Search messages with a query.

        Args:
            query: Gmail search query
            max_results: Maximum results

        Returns:
            List of matching messages
        """
        return self.get_messages(query=query, max_results=max_results)

    def get_unread(self, max_results: int = 25) -> list[Message]:
        """Get unread messages."""
        return self.get_messages(query="is:unread", max_results=max_results)

    def get_unread_inbox(self, max_results: int = 25) -> list[Message]:
        """Get unread messages in inbox."""
        return self.get_messages(query="is:unread in:inbox", max_results=max_results)

    def get_starred(self, max_results: int = 25) -> list[Message]:
        """Get starred messages."""
        return self.get_messages(query="is:starred", max_results=max_results)

    def get_important(self, max_results: int = 25) -> list[Message]:
        """Get important messages."""
        return self.get_messages(query="is:important", max_results=max_results)

    def get_sent(self, max_results: int = 25) -> list[Message]:
        """Get sent messages."""
        return self.get_messages(query="in:sent", max_results=max_results)

    def get_drafts(self, max_results: int = 25) -> list[Message]:
        """Get draft messages (as Messages; see list_drafts for Draft objects)."""
        return self.get_messages(query="in:drafts", max_results=max_results)

    def get_message(self, message_id: str) -> Message | None:
        """Get a specific message by ID, or None if it doesn't exist."""
        try:
            return self._get_message_by_id(message_id, include_body=True)
        except NotFoundError:
            return None

    def _get_message_by_id(self, message_id: str, include_body: bool = True) -> Message:
        """Internal: fetch and parse a message."""
        msg_data = execute(
            self.service.users()
            .messages()
            .get(
                userId=self.user_id,
                id=message_id,
                format="full" if include_body else "metadata",
            ),
            "gmail",
            "message",
            message_id,
        )

        return self._parse_message(msg_data, include_body)

    # ========== Threads ==========

    def get_thread(self, thread_id: str) -> Thread | None:
        """Get a full thread by ID, or None if it doesn't exist."""
        try:
            thread_data = execute(
                self.service.users()
                .threads()
                .get(userId=self.user_id, id=thread_id, format="full"),
                "gmail",
                "thread",
                thread_id,
            )
        except NotFoundError:
            return None
        return self._parse_thread(thread_data)

    def iter_threads(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
    ) -> Iterator[Thread]:
        """Lazily yield conversations matching criteria (fetched in batches)."""
        params: dict[str, Any] = {"userId": self.user_id}
        if query:
            params["q"] = str(query)
        if labels:
            params["labelIds"] = labels

        refs = paginate(
            self.service.users().threads().list,
            "threads",
            "gmail",
            max_items=max_results,
            max_page_size=500,
            **params,
        )
        while chunk := [ref["id"] for ref in islice(refs, BATCH_SIZE)]:
            requests = [
                self.service.users().threads().get(userId=self.user_id, id=tid, format="full")
                for tid in chunk
            ]
            for result in execute_batch(self.service, requests, "gmail", "thread", BATCH_SIZE):
                if isinstance(result, NotFoundError):
                    continue
                if isinstance(result, Exception):
                    raise result
                yield self._parse_thread(result)

    def get_threads(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int | None = 25,
    ) -> list[Thread]:
        """Get conversations matching criteria."""
        return list(self.iter_threads(query, labels, max_results))

    def _parse_thread(self, thread_data: dict) -> Thread:
        messages = [
            self._parse_message(msg_data, include_body=True)
            for msg_data in thread_data.get("messages", [])
        ]
        return Thread(
            id=thread_data["id"],
            messages=messages,
            snippet=thread_data.get("snippet", ""),
        )

    # ========== Labels ==========

    def get_labels(self) -> list[Label]:
        """Get all labels, with message and thread counts."""
        response = execute(self.service.users().labels().list(userId=self.user_id), "gmail")

        # The list has no counts; fetch each label, batched into one request
        requests = [
            self.service.users().labels().get(userId=self.user_id, id=label["id"])
            for label in response.get("labels", [])
        ]
        labels = []
        for result in execute_batch(self.service, requests, "gmail", "label", BATCH_SIZE):
            if isinstance(result, NotFoundError):
                continue
            if isinstance(result, Exception):
                raise result
            labels.append(GmailParser.parse_label(result))
        return labels

    def _get_label_id(self, label_name: str) -> str | None:
        """Get label ID by name (IDs are accepted too)."""
        if label_name in SYSTEM_LABELS or label_name.startswith("CATEGORY_"):
            return label_name
        if self._labels_cache is None:
            response = execute(self.service.users().labels().list(userId=self.user_id), "gmail")
            self._labels_cache = {l["name"]: l["id"] for l in response.get("labels", [])}

        # Check if it's already an ID
        if label_name in self._labels_cache.values():
            return label_name

        return self._labels_cache.get(label_name)

    def _require_label_ids(self, names: Sequence[str]) -> list[str]:
        ids = []
        for name in names:
            label_id = self._get_label_id(name)
            if label_id is None:
                raise ValidationError("labels", f"unknown label {name!r}")
            ids.append(label_id)
        return ids

    def create_label(
        self,
        name: str,
        show_in_label_list: bool = True,
        show_in_message_list: bool = True,
    ) -> Label:
        """
        Create a label. Use "Parent/Child" to nest it.

        Returns:
            The new Label
        """
        created = execute(
            self.service.users()
            .labels()
            .create(
                userId=self.user_id,
                body={
                    "name": name,
                    "labelListVisibility": "labelShow" if show_in_label_list else "labelHide",
                    "messageListVisibility": "show" if show_in_message_list else "hide",
                },
            ),
            "gmail",
            "label",
        )
        self._labels_cache = None
        return GmailParser.parse_label(created)

    def rename_label(self, label: str, new_name: str) -> Label:
        """Rename a label (by name or ID)."""
        (label_id,) = self._require_label_ids([label])
        updated = execute(
            self.service.users()
            .labels()
            .patch(userId=self.user_id, id=label_id, body={"name": new_name}),
            "gmail",
            "label",
            label_id,
        )
        self._labels_cache = None
        return GmailParser.parse_label(updated)

    def delete_label(self, label: str) -> bool:
        """
        Delete a label (by name or ID). Messages keep existing, unlabeled.

        Returns:
            True if deleted, False if no such label exists
        """
        label_id = self._get_label_id(label)
        if label_id is None:
            return False
        try:
            execute(
                self.service.users().labels().delete(userId=self.user_id, id=label_id),
                "gmail",
                "label",
                label_id,
            )
        except NotFoundError:
            return False
        finally:
            self._labels_cache = None
        return True

    def batch_modify(
        self,
        message_ids: Sequence[str],
        add_labels: Sequence[str] | None = None,
        remove_labels: Sequence[str] | None = None,
    ) -> int:
        """
        Add/remove labels on many messages in a few calls (1000 per call).

        Labels can be names or IDs ("UNREAD", "STARRED", "INBOX", "Work").
        Example: gmail.batch_modify(ids, remove_labels=["UNREAD"]) marks read.

        Returns:
            Number of message IDs sent
        """
        add_ids = self._require_label_ids(add_labels or [])
        remove_ids = self._require_label_ids(remove_labels or [])
        if not add_ids and not remove_ids:
            return 0

        ids = list(message_ids)
        for start in range(0, len(ids), BATCH_MODIFY_LIMIT):
            body: dict[str, Any] = {"ids": ids[start : start + BATCH_MODIFY_LIMIT]}
            if add_ids:
                body["addLabelIds"] = add_ids
            if remove_ids:
                body["removeLabelIds"] = remove_ids
            execute(
                self.service.users().messages().batchModify(userId=self.user_id, body=body),
                "gmail",
            )
        return len(ids)

    # ========== Filters ==========

    def list_filters(self) -> list[dict]:
        """List filters ({id, criteria, action} dicts as the API returns them)."""
        response = execute(
            self.service.users().settings().filters().list(userId=self.user_id), "gmail"
        )
        filters: list[dict] = response.get("filter", [])
        return filters

    def create_filter(self, criteria: dict, action: dict) -> dict:
        """
        Create a filter for incoming mail.

        Args:
            criteria: e.g. {"from": "alerts@example.com", "hasAttachment": True}
            action: e.g. {"addLabelIds": ["Alerts"], "removeLabelIds": ["INBOX"]}.
                Label names are resolved to IDs for you.

        Returns:
            The created filter
        """
        action = dict(action)
        for key in ("addLabelIds", "removeLabelIds"):
            if key in action:
                action[key] = self._require_label_ids(action[key])

        created: dict = execute(
            self.service.users()
            .settings()
            .filters()
            .create(userId=self.user_id, body={"criteria": criteria, "action": action}),
            "gmail",
            "filter",
        )
        return created

    def delete_filter(self, filter_id: str) -> bool:
        """Delete a filter. Returns False if it doesn't exist."""
        try:
            execute(
                self.service.users().settings().filters().delete(userId=self.user_id, id=filter_id),
                "gmail",
                "filter",
                filter_id,
            )
        except NotFoundError:
            return False
        return True

    # ========== Send ==========

    def get_signature(self, send_as_email: str | None = None) -> str | None:
        """
        Get the account's email signature.

        Args:
            send_as_email: Specific send-as email (default: primary)

        Returns:
            HTML signature or None
        """
        # Best effort: a missing signature shouldn't stop an email from sending
        try:
            email = send_as_email or self.email
            settings = execute(
                self.service.users()
                .settings()
                .sendAs()
                .get(userId=self.user_id, sendAsEmail=email),
                "gmail",
                "signature",
            )
            signature: str | None = settings.get("signature")
            return signature
        except GSuiteError as e:
            logger.debug(f"Could not get signature for {send_as_email}: {e}")
            return None

    def _compose(
        self,
        to: Sequence[str],
        subject: str,
        body: str,
        cc: Sequence[str] | None = None,
        bcc: Sequence[str] | None = None,
        html: bool = False,
        signature: bool = False,
        attachments: Sequence[OutgoingAttachment] | None = None,
        reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Build the API message body ({"raw", "threadId"})."""
        if signature:
            sig = self.get_signature()
            if sig:
                body = f"{body}<br><br>{sig}" if html else f"{body}\n\n{_html_to_text(sig)}"

        message = EmailMessage()
        message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)

        if reply_to:
            # Threading headers: without them the recipient sees a new
            # conversation even though it's in the sender's thread.
            original = self._get_message_by_id(reply_to, include_body=False)
            thread_id = thread_id or original.thread_id
            if original.rfc822_message_id:
                message["In-Reply-To"] = original.rfc822_message_id
                refs = f"{original.references or ''} {original.rfc822_message_id}".strip()
                message["References"] = refs
        message["Subject"] = subject

        if html:
            message.set_content(_html_to_text(body))
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        for item in attachments or []:
            if isinstance(item, tuple):
                filename, content = item
            else:
                path = Path(item)
                filename, content = path.name, path.read_bytes()
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            maintype, subtype = mime_type.split("/", 1)
            message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

        api_body: dict[str, Any] = {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        }
        if thread_id:
            api_body["threadId"] = thread_id
        return api_body

    def _send_composed(self, api_body: dict[str, Any]) -> Message:
        sent = execute(
            self.service.users().messages().send(userId=self.user_id, body=api_body),
            "gmail",
        )
        return self._get_message_by_id(sent["id"])

    def send(
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
        """
        Send an email.

        Args:
            to: Recipient email addresses
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            html: Whether body is HTML (a plain-text alternative is added)
            signature: Include account signature (appends to body)
            reply_to: Gmail message ID this replies to; sets the threading
                headers and thread (see reply() for a higher-level version)
            thread_id: Thread ID (for threading)
            attachments: File paths or (filename, bytes) tuples

        Returns:
            The sent message
        """
        return self._send_composed(
            self._compose(
                to, subject, body, cc, bcc, html, signature, attachments, reply_to, thread_id
            )
        )

    def _is_me(self, address: str) -> bool:
        return parseaddr(address)[1].lower() == self.email.lower()

    def reply(
        self,
        message: Message,
        body: str,
        html: bool = False,
        signature: bool = False,
        reply_all: bool = False,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> Message:
        """
        Reply to a message, in its thread for every participant.

        Goes to the Reply-To address (or the sender). Replying to a message
        you sent goes to its recipients instead of back to you.

        Args:
            reply_all: Also include the other To/Cc recipients

        Returns:
            The sent reply
        """
        if self._is_me(message.sender):
            to = [a for a in GmailParser._addresses(message.recipient) if not self._is_me(a)]
        else:
            to = [message.reply_to or message.sender]

        cc: list[str] = []
        if reply_all:
            seen = {parseaddr(a)[1].lower() for a in to}
            for address in [*GmailParser._addresses(message.recipient), *message.cc]:
                email = parseaddr(address)[1].lower()
                if email and email not in seen and not self._is_me(address):
                    seen.add(email)
                    cc.append(address)

        return self._send_composed(
            self._compose(
                to,
                _prefixed(message.subject, "Re:"),
                body,
                cc=cc or None,
                html=html,
                signature=signature,
                attachments=attachments,
                reply_to=message.id,
                thread_id=message.thread_id,
            )
        )

    def forward(
        self,
        message: Message,
        to: list[str],
        body: str = "",
        include_attachments: bool = True,
    ) -> Message:
        """
        Forward a message, quoting it below `body`.

        Args:
            include_attachments: Re-attach the original attachments

        Returns:
            The sent message
        """
        date = message.date.strftime("%a, %d %b %Y %H:%M") if message.date else ""
        original = message.plain or _html_to_text(message.html or "")
        quoted = (
            f"{body}\n\n---------- Forwarded message ---------\n"
            f"From: {message.sender}\nDate: {date}\nSubject: {message.subject}\n"
            f"To: {message.recipient}\n\n{original}"
        ).lstrip()

        attachments: list[OutgoingAttachment] = []
        if include_attachments:
            attachments = [(a.filename, a.download()) for a in message.attachments]

        return self.send(
            to=to,
            subject=_prefixed(message.subject, "Fwd:"),
            body=quoted,
            attachments=attachments or None,
        )

    # ========== Drafts ==========

    def create_draft(
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
        api_body = self._compose(to, subject, body, cc, bcc, html, False, attachments, reply_to)
        created = execute(
            self.service.users().drafts().create(userId=self.user_id, body={"message": api_body}),
            "gmail",
            "draft",
        )
        return Draft(id=created["id"], message=self._get_message_by_id(created["message"]["id"]))

    def get_draft(self, draft_id: str) -> Draft | None:
        """Get a draft, or None if it doesn't exist."""
        try:
            data = execute(
                self.service.users().drafts().get(userId=self.user_id, id=draft_id, format="full"),
                "gmail",
                "draft",
                draft_id,
            )
        except NotFoundError:
            return None
        return Draft(id=data["id"], message=self._parse_message(data["message"]))

    def list_drafts(self, max_results: int | None = 25) -> list[Draft]:
        """List drafts with their content (fetched in batches)."""
        refs = list(
            paginate(
                self.service.users().drafts().list,
                "drafts",
                "gmail",
                max_items=max_results,
                max_page_size=500,
                userId=self.user_id,
            )
        )
        requests = [
            self.service.users().drafts().get(userId=self.user_id, id=ref["id"], format="full")
            for ref in refs
        ]
        drafts = []
        for result in execute_batch(self.service, requests, "gmail", "draft", BATCH_SIZE):
            if isinstance(result, NotFoundError):
                continue
            if isinstance(result, Exception):
                raise result
            drafts.append(Draft(id=result["id"], message=self._parse_message(result["message"])))
        return drafts

    def send_draft(self, draft_id: str) -> Message:
        """Send a draft. Returns the sent message."""
        sent = execute(
            self.service.users().drafts().send(userId=self.user_id, body={"id": draft_id}),
            "gmail",
            "draft",
            draft_id,
        )
        return self._get_message_by_id(sent["id"])

    def delete_draft(self, draft_id: str) -> bool:
        """Discard a draft. Returns False if it doesn't exist."""
        try:
            execute(
                self.service.users().drafts().delete(userId=self.user_id, id=draft_id),
                "gmail",
                "draft",
                draft_id,
            )
        except NotFoundError:
            return False
        return True

    # ========== Profile ==========

    def get_profile(self) -> dict:
        """Get authenticated user's profile."""
        profile: dict = execute(self.service.users().getProfile(userId=self.user_id), "gmail")
        return profile

    @property
    def email(self) -> str:
        """Get authenticated user's email address (fetched once)."""
        if self._email is None:
            self._email = self.get_profile().get("emailAddress", "")
        return self._email

    # ========== Internal modification methods ==========

    def _modify_labels(
        self,
        message_id: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        """Internal: modify labels on a message."""
        body = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove

        if body:
            execute(
                self.service.users()
                .messages()
                .modify(userId=self.user_id, id=message_id, body=body),
                "gmail",
                "message",
                message_id,
            )

    def _trash_message(self, message_id: str) -> None:
        """Internal: trash a message."""
        execute(
            self.service.users().messages().trash(userId=self.user_id, id=message_id),
            "gmail",
            "message",
            message_id,
        )

    def _untrash_message(self, message_id: str) -> None:
        """Internal: untrash a message."""
        execute(
            self.service.users().messages().untrash(userId=self.user_id, id=message_id),
            "gmail",
            "message",
            message_id,
        )

    def _download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Internal: download attachment content."""
        attachment = execute(
            self.service.users()
            .messages()
            .attachments()
            .get(userId=self.user_id, messageId=message_id, id=attachment_id),
            "gmail",
            "attachment",
            attachment_id,
        )

        return base64.urlsafe_b64decode(attachment.get("data", ""))

    # ========== Parsing ==========

    def _parse_message(self, data: dict, include_body: bool = True) -> Message:
        """Parse Gmail API response to Message object."""
        # Use centralized parser
        msg = GmailParser.parse_message(data, include_body)

        # Link message and attachments to this client for fluent methods
        msg._gmail = self
        for att in msg.attachments:
            att._gmail = self

        return msg
