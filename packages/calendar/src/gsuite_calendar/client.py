"""Calendar client - high-level interface."""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.event import Event
from gsuite_calendar.parser import CalendarParser
from gsuite_core import GoogleAuth, authorized_http, execute, get_settings, paginate
from gsuite_core.exceptions import NotFoundError, ValidationError

SendUpdates = Literal["all", "externalOnly", "none"]


def _rfc3339(value: datetime) -> str:
    """UTC timestamp for the API. Naive datetimes are taken as UTC.

    Appending "Z" to isoformat() (as this used to) breaks aware datetimes:
    "2026-01-01T10:00:00+00:00Z" is rejected by the API.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


logger = logging.getLogger(__name__)


class Calendar:
    """
    High-level Calendar client.

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

    def __init__(self, auth: GoogleAuth, calendar_id: str = "primary"):
        """
        Initialize Calendar client.

        Args:
            auth: GoogleAuth instance with valid credentials
            calendar_id: Default calendar ID ("primary" for main calendar)
        """
        self.auth = auth
        self.calendar_id = calendar_id
        self._service = None

    @property
    def service(self) -> Any:
        """Lazy-load Calendar API service."""
        if self._service is None:
            self._service = build(
                "calendar", "v3", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._service

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
        """
        Lazily yield events in a time range, following result pages.

        Args:
            time_min: Start of range (default: now). Naive datetimes are UTC.
            time_max: End of range
            calendar_id: Calendar ID (default: primary)
            max_results: Maximum events to yield (None = all)
            single_events: Expand recurring events
            order_by: Sort order (startTime or updated)
        """
        cal_id = calendar_id or self.calendar_id

        params: dict[str, Any] = {
            "calendarId": cal_id,
            "timeMin": _rfc3339(time_min or datetime.now(UTC)),
            "singleEvents": single_events,
        }
        # The API only accepts orderBy=startTime for expanded single events
        if order_by != "startTime" or single_events:
            params["orderBy"] = order_by
        if time_max:
            params["timeMax"] = _rfc3339(time_max)

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
        """
        Get events in a time range.

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
        """
        Get upcoming events.

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

    @staticmethod
    def _time_bodies(
        start: datetime | date, end: datetime | date | None, all_day: bool
    ) -> tuple[dict[str, str], dict[str, str]]:
        """API start/end objects; end defaults to 1 hour (or the same day)."""
        if all_day or not isinstance(start, datetime):
            # datetime is a subclass of date: take .date() first, or an all-day
            # event built from a datetime sends "2026-01-01T10:00:00" as a date.
            start_date = start.date() if isinstance(start, datetime) else start
            end_date = end or start_date
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            # The API's end date is exclusive; `end` here is the last day
            return (
                {"date": start_date.isoformat()},
                {"date": (end_date + timedelta(days=1)).isoformat()},
            )

        if end is None:
            end = start + timedelta(hours=1)
        tz = get_settings().default_timezone
        # Naive datetimes are wall time in GSUITE_DEFAULT_TIMEZONE; aware ones
        # carry their own offset.
        return (
            {"dateTime": start.isoformat(), "timeZone": tz},
            {"dateTime": end.isoformat(), "timeZone": tz},
        )

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
        """
        Create a new event.

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
        start_body, end_body = self._time_bodies(start, end, all_day)

        event_body: dict[str, Any] = {"summary": summary, "start": start_body, "end": end_body}
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]
        if recurrence:
            event_body["recurrence"] = recurrence

        params: dict[str, Any] = {}
        if meet:
            event_body["conferenceData"] = {
                "createRequest": {
                    # Idempotency key: a retried insert won't create a second room
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
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
        """
        Change an event. Only the arguments you pass are updated.

        Moving an event: pass start (and end, or it becomes 1 hour long).
        attendees replaces the whole list.

        Returns:
            The updated Event
        """
        cal_id = calendar_id or self.calendar_id
        body: dict[str, Any] = {}
        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if attendees is not None:
            body["attendees"] = [{"email": email} for email in attendees]
        if start is not None:
            body["start"], body["end"] = self._time_bodies(start, end, all_day)
        elif end is not None:
            raise ValidationError("end", "pass start too when changing the time")
        if not body:
            raise ValidationError("event", "nothing to update")

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
        params: dict[str, Any] = {"calendarId": cal_id, "eventId": event_id}
        if time_min:
            params["timeMin"] = _rfc3339(time_min)
        if time_max:
            params["timeMax"] = _rfc3339(time_max)

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
    ) -> dict[str, list[dict[str, datetime | None]]]:
        """
        Busy intervals per calendar.

        Args:
            calendars: Calendar IDs or emails ("me" = your primary calendar).
                Default: this client's calendar.

        Returns:
            {calendar: [{"start": datetime, "end": datetime}, ...]}. A calendar
            you can't see comes back with no busy times and a logged warning.
        """
        ids = calendars or [self.calendar_id]
        query_ids = ["primary" if c == "me" else c for c in ids]
        response = execute(
            self.service.freebusy().query(
                body={
                    "timeMin": _rfc3339(time_min),
                    "timeMax": _rfc3339(time_max),
                    "items": [{"id": c} for c in query_ids],
                }
            ),
            "calendar",
        )

        result: dict[str, list[dict[str, datetime | None]]] = {}
        for requested, query_id in zip(ids, query_ids):
            info = response.get("calendars", {}).get(query_id, {})
            if info.get("errors"):
                logger.warning(f"Free/busy unavailable for {requested}: {info['errors']}")
            result[requested] = [
                {
                    "start": CalendarParser._parse_datetime(b.get("start")),
                    "end": CalendarParser._parse_datetime(b.get("end")),
                }
                for b in info.get("busy", [])
            ]
        return result

    def delete_event(
        self,
        event_id: str,
        calendar_id: str | None = None,
        send_updates: SendUpdates = "none",
    ) -> bool:
        """
        Delete an event.

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
            logger.warning(f"Event not found for deletion: {event_id}")
            return False
        logger.info(f"Deleted event {event_id}")
        return True

    # ========== Parsing ==========

    def _parse_event(self, data: dict, calendar_id: str) -> Event:
        """Parse Calendar API response to Event object."""
        return CalendarParser.parse_event(data, calendar_id)
