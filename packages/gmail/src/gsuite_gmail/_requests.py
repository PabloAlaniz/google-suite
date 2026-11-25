"""Gmail API request parameters and response folding, shared by the sync and async clients."""

import re
from collections.abc import Sequence
from typing import Any, Literal

from gsuite_core.channels import parse_expiration
from gsuite_core.exceptions import ValidationError
from gsuite_gmail.history import HistoryDelta, MailboxWatch
from gsuite_gmail.query import Query

MessageFormat = Literal["full", "metadata", "minimal"]
HistoryType = Literal["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"]
HISTORY_PAGE_SIZE = 500


def list_params(query: str | Query | None, labels: list[str] | None) -> dict[str, Any]:
    """q/labelIds for messages.list and threads.list."""
    params: dict[str, Any] = {}
    if query:
        params["q"] = str(query)
    if labels:
        params["labelIds"] = labels
    return params


def get_params(format: MessageFormat, headers: Sequence[str] | None) -> dict[str, Any]:
    """format/metadataHeaders for messages.get and threads.get."""
    if format not in ("full", "metadata", "minimal"):
        raise ValidationError("format", "use full, metadata or minimal")
    params: dict[str, Any] = {"format": format}
    if headers:
        if format != "metadata":
            raise ValidationError("headers", 'headers only apply to format="metadata"')
        params["metadataHeaders"] = list(headers)
    return params


def history_params(
    start_history_id: str,
    history_types: Sequence[HistoryType] | None,
    label_id: str | None,
) -> dict[str, Any]:
    """history.list parameters (paging aside)."""
    if not str(start_history_id).strip():
        raise ValidationError("start_history_id", "a history ID is required")
    params: dict[str, Any] = {"startHistoryId": str(start_history_id)}
    if history_types:
        params["historyTypes"] = list(history_types)
    if label_id:
        params["labelId"] = label_id
    return params


def add_history_page(delta: HistoryDelta, page: dict[str, Any]) -> None:
    """Fold one history.list page into ``delta`` (IDs in order, without repeats)."""
    for record in page.get("history", []):
        for key, bucket in (
            ("messagesAdded", delta.added),
            ("messagesDeleted", delta.deleted),
            ("labelsAdded", delta.labels_changed),
            ("labelsRemoved", delta.labels_changed),
        ):
            for change in record.get(key, []):
                message_id = change.get("message", {}).get("id")
                if message_id and message_id not in bucket:
                    bucket.append(message_id)
                if key == "messagesAdded" and message_id:
                    delta.added_labels[message_id] = change["message"].get("labelIds", [])
    if page.get("historyId"):
        delta.history_id = str(page["historyId"])


def finish_history(delta: HistoryDelta) -> HistoryDelta:
    """Drop deleted messages from the other lists."""
    gone = set(delta.deleted)
    delta.added = [m for m in delta.added if m not in gone]
    delta.labels_changed = [m for m in delta.labels_changed if m not in gone]
    delta.added_labels = {m: labels for m, labels in delta.added_labels.items() if m not in gone}
    return delta


LabelFilter = Literal["include", "exclude"]
_TOPIC = re.compile(r"projects/[^/\s]+/topics/[^/\s]+")


def watch_body(
    topic: str, label_ids: Sequence[str] | None, label_filter: LabelFilter
) -> dict[str, Any]:
    """The body of users.watch."""
    if not _TOPIC.fullmatch(topic):
        raise ValidationError("topic", 'expected "projects/<project>/topics/<topic>"')
    if label_filter not in ("include", "exclude"):
        raise ValidationError("label_filter", '"include" or "exclude"')
    body: dict[str, Any] = {"topicName": topic}
    if label_ids:
        body["labelIds"] = list(label_ids)
        body["labelFilterBehavior"] = label_filter.upper()
    return body


def parse_watch(data: dict[str, Any]) -> MailboxWatch:
    """A users.watch response."""
    return MailboxWatch(
        history_id=str(data.get("historyId", "")),
        expiration=parse_expiration(data.get("expiration")),
    )
