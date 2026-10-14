"""Calendar response parsers - converts API responses to domain entities."""

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
            start = CalendarParser._parse_datetime(
                start_data.get("dateTime"), start_data.get("timeZone")
            )
            end = CalendarParser._parse_datetime(end_data.get("dateTime"), end_data.get("timeZone"))

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
            meet_link=CalendarParser._meet_link(data),
            timezone=start_data.get("timeZone"),
            created=CalendarParser._parse_datetime(data.get("created")),
            updated=CalendarParser._parse_datetime(data.get("updated")),
            creator=data.get("creator", {}).get("email"),
            recurring_event_id=data.get("recurringEventId"),
        )

    @staticmethod
    def _meet_link(data: dict) -> str | None:
        """Video link from conferenceData (current) or hangoutLink (legacy)."""
        for entry in data.get("conferenceData", {}).get("entryPoints", []):
            if entry.get("entryPointType") == "video":
                uri: str | None = entry.get("uri")
                return uri
        link: str | None = data.get("hangoutLink")
        return link

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
    def _parse_datetime(dt_string: str | None, time_zone: str | None = None) -> datetime | None:
        """Parse an ISO datetime string to an aware datetime.

        A value without an offset is local time in ``time_zone`` (the IANA
        name an event's start/end carries), or UTC when there is none or it
        is unknown. Mixing naive and aware values would make arithmetic such
        as ``Event.duration_minutes`` raise.
        """
        if not dt_string:
            return None
        try:
            # Handle Z suffix and timezone offset
            parsed = datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is not None:
            return parsed
        return parsed.replace(tzinfo=CalendarParser._zone(time_zone))

    @staticmethod
    def _zone(name: str | None) -> tzinfo:
        """The IANA zone ``name``, or UTC if it is missing or unknown."""
        if not name:
            return UTC
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
            # Unknown, malformed, or not a valid path component
            return UTC

    @staticmethod
    def _parse_date(date_string: str | None) -> datetime | None:
        """Parse ISO date string to datetime object."""
        if not date_string:
            return None
        try:
            return datetime.fromisoformat(date_string)
        except (ValueError, TypeError):
            return None
