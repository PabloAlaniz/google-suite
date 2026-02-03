"""Calendar response parsers - converts API responses to domain entities."""

from datetime import datetime

from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.event import Attendee, Event


class CalendarParser:
    """Parser for Calendar API responses."""

    @staticmethod
    def parse_event(data: dict, calendar_id: str) -> Event:
        """
        Parse Calendar API response to Event entity.

        Args:
            data: Raw API response dict
            calendar_id: Calendar ID the event belongs to

        Returns:
            Event entity
        """
        # Parse start/end times
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        all_day = "date" in start_data

        if all_day:
            start = CalendarParser._parse_date(start_data.get("date"))
            end = CalendarParser._parse_date(end_data.get("date"))
        else:
            start = CalendarParser._parse_datetime(start_data.get("dateTime"))
            end = CalendarParser._parse_datetime(end_data.get("dateTime"))

        # Parse attendees
        attendees = [
            CalendarParser.parse_attendee(att_data) for att_data in data.get("attendees", [])
        ]

        return Event(
            id=data["id"],
            summary=data.get("summary", ""),
            description=data.get("description"),
            location=data.get("location"),
            start=start,
            end=end,
            all_day=all_day,
            recurring="recurringEventId" in data,
            recurrence=data.get("recurrence"),
            attendees=attendees,
            organizer=data.get("organizer", {}).get("email"),
            calendar_id=calendar_id,
            html_link=data.get("htmlLink"),
            status=data.get("status", "confirmed"),
        )

    @staticmethod
    def parse_attendee(data: dict) -> Attendee:
        """
        Parse attendee data to Attendee entity.

        Args:
            data: Raw attendee dict from API

        Returns:
            Attendee entity
        """
        return Attendee(
            email=data.get("email", ""),
            name=data.get("displayName"),
            response_status=data.get("responseStatus", "needsAction"),
            organizer=data.get("organizer", False),
            self_=data.get("self", False),
        )

    @staticmethod
    def parse_calendar(data: dict) -> CalendarEntity:
        """
        Parse Calendar API response to CalendarEntity.

        Args:
            data: Raw API response dict

        Returns:
            CalendarEntity
        """
        return CalendarEntity(
            id=data["id"],
            summary=data.get("summary", ""),
            description=data.get("description"),
            time_zone=data.get("timeZone"),
            primary=data.get("primary", False),
            access_role=data.get("accessRole", "reader"),
            background_color=data.get("backgroundColor"),
            foreground_color=data.get("foregroundColor"),
        )

    @staticmethod
    def _parse_datetime(dt_string: str | None) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not dt_string:
            return None
        try:
            # Handle Z suffix and timezone offset
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(date_string: str | None) -> datetime | None:
        """Parse ISO date string to datetime object."""
        if not date_string:
            return None
        try:
            return datetime.fromisoformat(date_string)
        except (ValueError, TypeError):
            return None
