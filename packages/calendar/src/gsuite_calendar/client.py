"""Calendar client - high-level interface."""

import logging
from datetime import date, datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.event import Event
from gsuite_calendar.parser import CalendarParser
from gsuite_core import GoogleAuth, get_settings

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
    def service(self):
        """Lazy-load Calendar API service."""
        if self._service is None:
            self._service = build("calendar", "v3", credentials=self.auth.credentials)
        return self._service

    # ========== Event retrieval ==========

    def get_events(
        self,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int = 250,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> list[Event]:
        """
        Get events in a time range.

        Args:
            time_min: Start of range (default: now)
            time_max: End of range
            calendar_id: Calendar ID (default: primary)
            max_results: Maximum events to return
            single_events: Expand recurring events
            order_by: Sort order (startTime or updated)

        Returns:
            List of Event objects
        """
        cal_id = calendar_id or self.calendar_id
        time_min = time_min or datetime.utcnow()

        request_params = {
            "calendarId": cal_id,
            "timeMin": time_min.isoformat() + "Z",
            "maxResults": max_results,
            "singleEvents": single_events,
            "orderBy": order_by,
        }

        if time_max:
            request_params["timeMax"] = time_max.isoformat() + "Z"

        response = self.service.events().list(**request_params).execute()

        events = []
        for event_data in response.get("items", []):
            events.append(self._parse_event(event_data, cal_id))

        return events

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
        time_min = datetime.utcnow()
        time_max = time_min + timedelta(days=days)

        return self.get_events(
            time_min=time_min,
            time_max=time_max,
            calendar_id=calendar_id,
            max_results=max_results,
        )

    def get_today(self, calendar_id: str | None = None) -> list[Event]:
        """Get today's events."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        return self.get_events(time_min=today, time_max=tomorrow, calendar_id=calendar_id)

    def get_event(self, event_id: str, calendar_id: str | None = None) -> Event | None:
        """Get a specific event by ID."""
        cal_id = calendar_id or self.calendar_id

        try:
            event_data = (
                self.service.events()
                .get(
                    calendarId=cal_id,
                    eventId=event_id,
                )
                .execute()
            )
            return self._parse_event(event_data, cal_id)
        except HttpError as e:
            if e.resp.status == 404:
                logger.debug(f"Event not found: {event_id}")
                return None
            logger.error(f"Error getting event {event_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting event {event_id}: {e}")
            return None

    # ========== Calendars ==========

    def get_calendars(self) -> list[CalendarEntity]:
        """Get all accessible calendars."""
        response = self.service.calendarList().list().execute()

        return [CalendarParser.parse_calendar(cal_data) for cal_data in response.get("items", [])]

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

        Returns:
            Created Event
        """
        cal_id = calendar_id or self.calendar_id

        # Handle all-day events
        if all_day or isinstance(start, date) and not isinstance(start, datetime):
            start_body = {
                "date": start.isoformat() if isinstance(start, date) else start.date().isoformat()
            }
            end_date = end or start
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            end_body = {"date": (end_date + timedelta(days=1)).isoformat()}
        else:
            if end is None:
                end = start + timedelta(hours=1)
            settings = get_settings()
            tz = settings.default_timezone
            start_body = {"dateTime": start.isoformat(), "timeZone": tz}
            end_body = {"dateTime": end.isoformat(), "timeZone": tz}

        event_body = {
            "summary": summary,
            "start": start_body,
            "end": end_body,
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        created = (
            self.service.events()
            .insert(
                calendarId=cal_id,
                body=event_body,
            )
            .execute()
        )

        return self._parse_event(created, cal_id)

    def delete_event(self, event_id: str, calendar_id: str | None = None) -> bool:
        """Delete an event."""
        cal_id = calendar_id or self.calendar_id

        try:
            self.service.events().delete(
                calendarId=cal_id,
                eventId=event_id,
            ).execute()
            logger.info(f"Deleted event {event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Event not found for deletion: {event_id}")
            else:
                logger.error(f"Error deleting event {event_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting event {event_id}: {e}")
            return False

    # ========== Parsing ==========

    def _parse_event(self, data: dict, calendar_id: str) -> Event:
        """Parse Calendar API response to Event object."""
        return CalendarParser.parse_event(data, calendar_id)
