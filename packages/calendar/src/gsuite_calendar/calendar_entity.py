"""Calendar entity."""

from dataclasses import dataclass


@dataclass
class CalendarEntity:
    """
    A calendar.

    Represents a single calendar (primary or shared).
    """

    id: str
    summary: str
    description: str | None = None
    time_zone: str | None = None
    primary: bool = False
    access_role: str = "reader"  # freeBusyReader, reader, writer, owner
    background_color: str | None = None
    foreground_color: str | None = None

    @property
    def is_primary(self) -> bool:
        """Check if this is the user's primary calendar."""
        return self.primary

    @property
    def is_writable(self) -> bool:
        """Check if user can write to this calendar."""
        return self.access_role in ("writer", "owner")
