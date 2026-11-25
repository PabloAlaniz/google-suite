"""What changed in a mailbox since a history ID (incremental sync)."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class HistoryDelta:
    """Message IDs that changed since a history ID, and the ID to resume from.

    A message added and then deleted in the same window appears only in
    ``deleted``; ``labels_changed`` leaves out deleted messages too. Keep
    ``history_id`` and pass it to the next ``Gmail.history``.
    """

    added: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    labels_changed: list[str] = field(default_factory=list)
    history_id: str | None = None
    # Label IDs each added message had when it arrived, e.g. to skip some labels
    added_labels: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class IdPage:
    """One page of message IDs, and the token for the next (None on the last page).

    Store ``next_page_token`` to resume a long listing later, e.g. across runs.
    """

    ids: list[str] = field(default_factory=list)
    next_page_token: str | None = None


@dataclass
class MailboxWatch:
    """A mailbox being watched: Gmail publishes to a Pub/Sub topic when it changes.

    ``history_id`` is where the first ``Gmail.history`` call after a
    notification starts. Gmail stops publishing at ``expiration`` (about a week
    later): call ``watch`` again before then, e.g. once a day.
    """

    history_id: str
    expiration: datetime | None = None
