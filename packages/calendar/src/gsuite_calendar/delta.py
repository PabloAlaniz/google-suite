"""What changed in a calendar since a sync token."""

from dataclasses import dataclass, field

from gsuite_calendar.event import Event


@dataclass
class EventsDelta:
    """Events changed or cancelled since a sync token (every event on the first sync).

    Deleted events come back cancelled, often with little more than their ID.
    Keep ``sync_token`` and pass it to the next ``Calendar.sync``.
    """

    changed: list[Event] = field(default_factory=list)
    cancelled: list[Event] = field(default_factory=list)
    sync_token: str | None = None
