"""Tests for Calendar parser."""

import pytest

from gsuite_calendar.parser import CalendarParser


class TestCalendarParser:
    """Tests for CalendarParser."""

    def test_parse_event_basic(self):
        """Test parsing a basic event."""
        data = {
            "id": "event123",
            "summary": "Team Meeting",
            "description": "Weekly sync",
            "location": "Conference Room A",
            "status": "confirmed",
            "htmlLink": "https://calendar.google.com/event?eid=abc",
            "start": {"dateTime": "2026-02-03T10:00:00Z"},
            "end": {"dateTime": "2026-02-03T11:00:00Z"},
        }

        event = CalendarParser.parse_event(data, "primary")

        assert event.id == "event123"
        assert event.summary == "Team Meeting"
        assert event.description == "Weekly sync"
        assert event.location == "Conference Room A"
        assert event.calendar_id == "primary"
        assert event.all_day is False
        assert event.start.hour == 10

    def test_parse_event_all_day(self):
        """Test parsing an all-day event."""
        data = {
            "id": "event456",
            "summary": "Company Holiday",
            "start": {"date": "2026-02-15"},
            "end": {"date": "2026-02-16"},
        }

        event = CalendarParser.parse_event(data, "primary")

        assert event.id == "event456"
        assert event.all_day is True
        assert event.start.day == 15

    def test_parse_event_with_attendees(self):
        """Test parsing event with attendees."""
        data = {
            "id": "event789",
            "summary": "Project Review",
            "start": {"dateTime": "2026-02-03T14:00:00Z"},
            "end": {"dateTime": "2026-02-03T15:00:00Z"},
            "attendees": [
                {
                    "email": "alice@example.com",
                    "displayName": "Alice",
                    "responseStatus": "accepted",
                    "organizer": True,
                },
                {
                    "email": "bob@example.com",
                    "responseStatus": "tentative",
                },
            ],
        }

        event = CalendarParser.parse_event(data, "primary")

        assert len(event.attendees) == 2
        assert event.attendees[0].email == "alice@example.com"
        assert event.attendees[0].name == "Alice"
        assert event.attendees[0].response_status == "accepted"
        assert event.attendees[0].organizer is True
        assert event.attendees[1].response_status == "tentative"

    def test_parse_event_recurring(self):
        """Test parsing a recurring event."""
        data = {
            "id": "event_instance",
            "recurringEventId": "master_event",
            "summary": "Daily Standup",
            "start": {"dateTime": "2026-02-03T09:00:00Z"},
            "end": {"dateTime": "2026-02-03T09:15:00Z"},
        }

        event = CalendarParser.parse_event(data, "primary")

        assert event.recurring is True

    def test_parse_calendar(self):
        """Test parsing a calendar."""
        data = {
            "id": "primary",
            "summary": "Personal Calendar",
            "description": "My main calendar",
            "timeZone": "America/New_York",
            "primary": True,
            "accessRole": "owner",
            "backgroundColor": "#4285f4",
            "foregroundColor": "#ffffff",
        }

        calendar = CalendarParser.parse_calendar(data)

        assert calendar.id == "primary"
        assert calendar.summary == "Personal Calendar"
        assert calendar.primary is True
        assert calendar.access_role == "owner"
        assert calendar.time_zone == "America/New_York"

    def test_parse_attendee(self):
        """Test parsing an attendee."""
        data = {
            "email": "user@example.com",
            "displayName": "Test User",
            "responseStatus": "accepted",
            "organizer": False,
            "self": True,
        }

        attendee = CalendarParser.parse_attendee(data)

        assert attendee.email == "user@example.com"
        assert attendee.name == "Test User"
        assert attendee.response_status == "accepted"
        assert attendee.self_ is True
