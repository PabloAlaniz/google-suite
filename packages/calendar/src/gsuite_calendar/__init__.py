"""Google Suite Calendar - Simple Calendar API client."""

__version__ = "0.1.0"

from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.client import Calendar
from gsuite_calendar.event import Event

__all__ = [
    "Calendar",
    "Event",
    "CalendarEntity",
]
