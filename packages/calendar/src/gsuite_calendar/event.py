"""Calendar Event entity."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Attendee:
    """Event attendee."""

    email: str
    name: str | None = None
    response_status: str = "needsAction"  # needsAction, declined, tentative, accepted
    organizer: bool = False
    self_: bool = False


@dataclass
class Event:
    """
    Calendar event.

    Represents a single calendar event with all its metadata.
    """

    id: str
    summary: str
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    recurring: bool = False
    recurrence: list[str] | None = None
    attendees: list[Attendee] = field(default_factory=list)
    organizer: str | None = None
    calendar_id: str = "primary"
    html_link: str | None = None
    status: str = "confirmed"  # confirmed, tentative, cancelled

    @property
    def duration_minutes(self) -> int | None:
        """Get event duration in minutes."""
        if self.start and self.end:
            delta = self.end - self.start
            return int(delta.total_seconds() / 60)
        return None

    @property
    def is_all_day(self) -> bool:
        """Check if this is an all-day event."""
        return self.all_day

    @property
    def is_recurring(self) -> bool:
        """Check if this is a recurring event."""
        return self.recurring or bool(self.recurrence)
