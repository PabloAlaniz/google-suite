"""What changed in a mailbox since a history ID (incremental sync)."""

from dataclasses import dataclass, field


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
