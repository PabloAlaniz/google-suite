"""Gmail tools: search, read, send, reply, forward, drafts, labels and trash."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.serialize import draft_summary, message_full, message_summary, thread_full, to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    DESTRUCTIVE,
    READ,
    WRITE,
    ToolDecorator,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the gmail tools on the server."""
    _register_mail(tool, svc)
    _register_listings(tool, svc)
    _register_actions(tool, svc)
    _register_destructive(tool, svc)


def _register_mail(tool: ToolDecorator, svc: Services) -> None:
    """Search, read, send, reply and draft."""

    @tool(READ)
    def gmail_search(query: str, max_results: int = 10) -> dict[str, Any]:
        """Search Gmail with Gmail query syntax (from:, to:, subject:, is:unread,
        has:attachment, newer_than:7d, label:...). Returns summaries without bodies.
        """
        return results(
            [message_summary(m) for m in svc.gmail.search(query, max_results=max_results)]
        )

    @tool(READ)
    def gmail_read(message_id: str) -> dict[str, Any]:
        """Read one email: headers, text body and attachment list."""
        message = svc.gmail.get_message(message_id)
        if message is None:
            raise ToolError(f"No message {message_id}")
        return message_full(message)

    @tool(WRITE)
    def gmail_send(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
    ) -> dict[str, Any]:
        """Send an email. Confirm recipients and content with the user first."""
        sent = svc.gmail.send(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_reply(message_id: str, body: str, reply_all: bool = False) -> dict[str, Any]:
        """Reply in the thread of a message. Confirm the content with the user first."""
        message = svc.gmail.get_message(message_id)
        if message is None:
            raise ToolError(f"No message {message_id}")
        sent = svc.gmail.reply(message, body, reply_all=reply_all)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_create_draft(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
    ) -> dict[str, Any]:
        """Save a draft without sending it (safe way to propose an email)."""
        draft = svc.gmail.create_draft(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)
        return {"draft_id": draft.id}


def _register_listings(tool: ToolDecorator, svc: Services) -> None:
    """Threads, labels and drafts."""

    @tool(READ)
    def gmail_read_thread(thread_id: str) -> dict[str, Any]:
        """Read a whole conversation: every message with its text body, oldest first.
        Messages carry their `thread_id`, so search or read a message first.
        """
        thread = svc.gmail.get_thread(thread_id)
        if thread is None:
            raise ToolError(f"No thread {thread_id}")
        return thread_full(thread)

    @tool(READ)
    def gmail_list_labels() -> dict[str, Any]:
        """Every label (system and user) with its ID and unread counts."""
        return results(to_json(svc.gmail.get_labels()))

    @tool(READ)
    def gmail_list_drafts(max_results: int = 25) -> dict[str, Any]:
        """Saved drafts as summaries with their `draft_id`."""
        return results([draft_summary(d) for d in svc.gmail.list_drafts(max_results=max_results)])


def _register_actions(tool: ToolDecorator, svc: Services) -> None:
    """Label, forward, send drafts and create labels."""

    @tool(WRITE)
    def gmail_modify_labels(
        message_ids: list[str],
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add or remove labels on messages; labels are names or IDs. Recipes:
        archive = remove ["INBOX"]; mark read = remove ["UNREAD"]; mark unread =
        add ["UNREAD"]; star = add ["STARRED"]; file = add ["Work"]. Use
        gmail_trash to delete.
        """
        if not add and not remove:
            raise ToolError("Pass labels to add and/or remove")
        count = svc.gmail.batch_modify(message_ids, add_labels=add, remove_labels=remove)
        return {"modified": count}

    @tool(WRITE)
    def gmail_forward(
        message_id: str, to: list[str], body: str = "", include_attachments: bool = True
    ) -> dict[str, Any]:
        """Forward a message with an optional note above it. Confirm recipients
        with the user first.
        """
        message = svc.gmail.get_message(message_id)
        if message is None:
            raise ToolError(f"No message {message_id}")
        sent = svc.gmail.forward(message, to=to, body=body, include_attachments=include_attachments)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_send_draft(draft_id: str) -> dict[str, Any]:
        """Send a saved draft. Confirm with the user first."""
        sent = svc.gmail.send_draft(draft_id)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_create_label(name: str) -> dict[str, Any]:
        """Create a label; "Parent/Child" nests it."""
        return to_json(svc.gmail.create_label(name))  # type: ignore[no-any-return]


def _register_destructive(tool: ToolDecorator, svc: Services) -> None:
    """Trash messages and discard drafts."""

    @tool(DESTRUCTIVE)
    def gmail_trash(message_ids: list[str]) -> dict[str, Any]:
        """Move messages to the trash (Gmail empties it after 30 days). Confirm
        with the user first.
        """
        trashed, missing = [], []
        for message_id in message_ids:
            message = svc.gmail.get_message(message_id)
            if message is None:
                missing.append(message_id)
            else:
                message.trash()
                trashed.append(message_id)
        return {"trashed": trashed, "missing": missing}

    @tool(DESTRUCTIVE)
    def gmail_delete_draft(draft_id: str) -> dict[str, Any]:
        """Discard a draft for good."""
        if not svc.gmail.delete_draft(draft_id):
            raise ToolError(f"No draft {draft_id}")
        return {"deleted": draft_id}
