"""Calendar client - high-level interface."""

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from gsuite_calendar._requests import (
    FreeBusy,
    details,
    free_busy_body,
    free_busy_ids,
    list_params,
    meet_request,
    parse_free_busy,
    patch_body,
    range_params,
    time_bodies,
)
from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.event import Event
from gsuite_calendar.parser import CalendarParser
from gsuite_core import GoogleAuth, execute, get_settings, paginate
from gsuite_core.exceptions import NotFoundError
from gsuite_core.service import GoogleService

SendUpdates = Literal["all", "externalOnly", "none"]


logger = logging.getLogger(__name__)


class Calendar:
    """High-level Calendar client.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        cal = Calendar(auth)

        # Get upcoming events
        for event in cal.get_upcoming(days=7):
            print(f"{event.start}: {event.summary}")

        # Create event
        cal.create_event(
            summary="Meeting",
            start=datetime(2026, 1, 30, 10, 0),
            end=datetime(2026, 1, 30, 11, 0),
        )
    """

    service = GoogleService("calendar", "v3")

    def __init__(self, auth: GoogleAuth, calendar_id: str = "primary"):
        """Initialize Calendar client.

        Args:
            auth: GoogleAuth instance with valid credentials
            calendar_id: Default calendar ID ("primary" for main calendar)
        """
        self.auth = auth
        self.calendar_id = calendar_id

    # ========== Event retrieval ==========

    def iter_events(
        self,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int | None = 250,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> Iterator[Event]:
        """Lazily yield events in a time range, following result pages.

        Args:
            time_min: Start of range (default: now). Naive datetimes are UTC.
            time_max: End of range
            calendar_id: Calendar ID (default: primary)
            max_results: Maximum events to yield (None = all)
            single_events: Expand recurring events
            order_by: Sort order (startTime or updated)
        """
        cal_id = calendar_id or self.calendar_id

        params = {"calendarId": cal_id, **list_params(time_min, time_max, single_events, order_by)}

        items = paginate(
            self.service.events().list,
            "items",
            "calendar",
            max_items=max_results,
            max_page_size=2500,
            **params,
        )
        for event_data in items:
            yield self._parse_event(event_data, cal_id)

    def get_events(
        self,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int | None = 250,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> list[Event]:
        """Get events in a time range.

        Args:
            time_min: Start of range (default: now). Naive datetimes are UTC.
            time_max: End of range
            calendar_id: Calendar ID (default: primary)
            max_results: Maximum events to return (None = all)
            single_events: Expand recurring events
            order_by: Sort order (startTime or updated)

        Returns:
            List of Event objects
        """
        return list(
            self.iter_events(time_min, time_max, calendar_id, max_results, single_events, order_by)
        )

    def get_upcoming(
        self,
        days: int = 7,
        calendar_id: str | None = None,
        max_results: int = 100,
    ) -> list[Event]:
        """Get upcoming events.

        Args:
            days: Number of days ahead (default: 7)
            calendar_id: Calendar ID
            max_results: Maximum events

        Returns:
            List of upcoming events
        """
        time_min = datetime.now(UTC)
        time_max = time_min + timedelta(days=days)

        return self.get_events(
            time_min=time_min,
            time_max=time_max,
            calendar_id=calendar_id,
            max_results=max_results,
        )

    def get_today(self, calendar_id: str | None = None) -> list[Event]:
        """Get today's events, where "today" is in GSUITE_DEFAULT_TIMEZONE."""
        tz = ZoneInfo(get_settings().default_timezone)
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        return self.get_events(time_min=today, time_max=tomorrow, calendar_id=calendar_id)

    def get_event(self, event_id: str, calendar_id: str | None = None) -> Event | None:
        """Get a specific event by ID."""
        cal_id = calendar_id or self.calendar_id

        try:
            event_data = execute(
                self.service.events().get(calendarId=cal_id, eventId=event_id),
                "calendar",
                "event",
                event_id,
            )
        except NotFoundError:
            return None
        return self._parse_event(event_data, cal_id)

    # ========== Calendars ==========

    def get_calendars(self) -> list[CalendarEntity]:
        """Get all accessible calendars."""
        items = paginate(self.service.calendarList().list, "items", "calendar", max_page_size=250)
        return [CalendarParser.parse_calendar(cal_data) for cal_data in items]

    # ========== Create/Update ==========

    def create_event(
        self,
        summary: str,
        start: datetime | date,
        end: datetime | date | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str | None = None,
        all_day: bool = False,
        recurrence: list[str] | None = None,
        meet: bool = False,
        send_updates: SendUpdates = "none",
    ) -> Event:
        """Create a new event.

        Args:
            summary: Event title
            start: Start time (datetime) or date (for all-day)
            end: End time (default: start + 1 hour)
            description: Event description
            location: Event location
            attendees: List of attendee emails
            calendar_id: Calendar to create in
            all_day: Create as all-day event
            recurrence: RRULE lines, e.g. ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"]
            meet: Attach a new Google Meet link (see Event.meet_link)
            send_updates: Email attendees: "all", "externalOnly" or "none"

        Returns:
            Created Event
        """
        cal_id = calendar_id or self.calendar_id
        start_body, end_body = time_bodies(start, end, all_day)
        event_body: dict[str, Any] = {
            "summary": summary,
            "start": start_body,
            "end": end_body,
            **details(description, location, attendees, recurrence),
        }
        params: dict[str, Any] = {}
        if meet:
            event_body["conferenceData"] = meet_request()
            params["conferenceDataVersion"] = 1

        created = execute(
            self.service.events().insert(
                calendarId=cal_id, body=event_body, sendUpdates=send_updates, **params
            ),
            "calendar",
            "event",
        )

        return self._parse_event(created, cal_id)

    def quick_add(
        self, text: str, calendar_id: str | None = None, send_updates: SendUpdates = "none"
    ) -> Event:
        """Create an event from natural language: "Lunch with Ana tomorrow at 1pm"."""
        cal_id = calendar_id or self.calendar_id
        created = execute(
            self.service.events().quickAdd(calendarId=cal_id, text=text, sendUpdates=send_updates),
            "calendar",
            "event",
        )
        return self._parse_event(created, cal_id)

    def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        all_day: bool = False,
        calendar_id: str | None = None,
        send_updates: SendUpdates = "none",
    ) -> Event:
        """Change an event. Only the arguments you pass are updated.

        Moving an event: pass start (and end, or it becomes 1 hour long).
        attendees replaces the whole list.

        Returns:
            The updated Event
        """
        cal_id = calendar_id or self.calendar_id
        body = patch_body(
            summary, (start, end, all_day), details(description, location, attendees, patch=True)
        )

        updated = execute(
            self.service.events().patch(
                calendarId=cal_id, eventId=event_id, body=body, sendUpdates=send_updates
            ),
            "calendar",
            "event",
            event_id,
        )
        return self._parse_event(updated, cal_id)

    def get_instances(
        self,
        event_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int | None = 250,
        calendar_id: str | None = None,
    ) -> list[Event]:
        """Occurrences of a recurring event (optionally within a time range)."""
        cal_id = calendar_id or self.calendar_id
        params = {"calendarId": cal_id, "eventId": event_id, **range_params(time_min, time_max)}

        items = paginate(
            self.service.events().instances,
            "items",
            "calendar",
            max_items=max_results,
            max_page_size=2500,
            **params,
        )
        return [self._parse_event(item, cal_id) for item in items]

    def get_free_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        calendars: list[str] | None = None,
    ) -> FreeBusy:
        """Busy intervals per calendar.

        Args:
            calendars: Calendar IDs or emails ("me" = your primary calendar).
                Default: this client's calendar.

        Returns:
            {calendar: [{"start": datetime, "end": datetime}, ...]}. A calendar
            you can't see comes back with no busy times and a logged warning.
        """
        ids = calendars or [self.calendar_id]
        response = execute(
            self.service.freebusy().query(
                body=free_busy_body(time_min, time_max, free_busy_ids(ids))
            ),
            "calendar",
        )
        return parse_free_busy(response, ids)

    def delete_event(
        self,
        event_id: str,
        calendar_id: str | None = None,
        send_updates: SendUpdates = "none",
    ) -> bool:
        """Delete an event.

        Args:
            send_updates: Email attendees about the cancellation: "all",
                "externalOnly" or "none"

        Returns:
            True if deleted, False if it didn't exist. Other failures (auth,
            rate limit, ...) raise instead of looking like "not found".
        """
        cal_id = calendar_id or self.calendar_id

        try:
            execute(
                self.service.events().delete(
                    calendarId=cal_id, eventId=event_id, sendUpdates=send_updates
                ),
                "calendar",
                "event",
                event_id,
            )
        except NotFoundError:
            logger.warning("Event not found for deletion: %s", event_id)
            return False
        logger.info("Deleted event %s", event_id)
        return True

    # ========== Parsing ==========

    def _parse_event(self, data: dict[str, Any], calendar_id: str) -> Event:
        """Parse Calendar API response to Event object."""
        return CalendarParser.parse_event(data, calendar_id)
