"""SDK entities as JSON-ready dicts for tool results."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any

# Bulky or internal fields agents don't need
SKIP = {"raw", "html", "plain", "messages", "references"}


def to_json(value: Any, *, skip: set[str] = SKIP) -> Any:
    """Dataclasses become dicts (minus raw/private fields), dates become ISO strings."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_json(getattr(value, f.name), skip=skip)
            for f in dataclasses.fields(value)
            if not f.name.startswith("_") and f.name not in skip
        }
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_json(v, skip=skip) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_json(v, skip=skip) for v in value]
    return value


def message_summary(message: Any) -> dict[str, Any]:
    """A Gmail message without its body: what a search result needs."""
    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "subject": message.subject,
        "sender": message.sender,
        "date": to_json(message.date),
        "snippet": message.snippet,
        "labels": list(message.labels),
        "attachments": [a.filename for a in message.attachments],
    }


def message_full(message: Any) -> dict[str, Any]:
    """A Gmail message with its text body and attachment metadata."""
    return {
        **message_summary(message),
        "recipient": message.recipient,
        "cc": message.cc,
        "body": message.body,
        "attachments": [
            {"id": a.id, "filename": a.filename, "mime_type": a.mime_type, "size": a.size}
            for a in message.attachments
        ],
    }
