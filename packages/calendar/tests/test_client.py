"""Tests for Calendar client."""

from datetime import datetime
from unittest.mock import Mock, patch

from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.client import Calendar
from gsuite_calendar.event import Event


class TestCalendarInit:
    """Tests for Calendar client initialization."""

    def test_init_with_auth(self):
        """Test Calendar client initialization."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        assert cal.auth is mock_auth
        assert cal.calendar_id == "primary"
        assert cal._service is None

    def test_init_with_custom_calendar(self):
        """Test Calendar with custom calendar_id."""
        mock_auth = Mock()
        cal = Calendar(mock_auth, calendar_id="work@example.com")

        assert cal.calendar_id == "work@example.com"


class TestCalendarService:
    """Tests for Calendar service property."""

    @patch("gsuite_calendar.client.build")
    def test_lazy_service_creation(self, mock_build):
        """Test service is created lazily."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_service = Mock()
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)

        # Service not created yet
        mock_build.assert_not_called()

        # Access service
        service = cal.service

        # Now it's created
        mock_build.assert_called_once_with("calendar", "v3", credentials=mock_auth.credentials)
        assert service is mock_service


class TestGetEvents:
    """Tests for get_events method."""

    @patch("gsuite_calendar.client.build")
    def test_get_events_empty(self, mock_build):
        """Test get_events with no results."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().list().execute.return_value = {"items": []}
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        events = cal.get_events()

        assert events == []

    @patch("gsuite_calendar.client.build")
    def test_get_events_with_time_range(self, mock_build):
        """Test get_events with time range."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.events().list
        mock_list().execute.return_value = {"items": []}
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)

        time_min = datetime(2026, 1, 28, 0, 0, 0)
        time_max = datetime(2026, 1, 29, 0, 0, 0)
        cal.get_events(time_min=time_min, time_max=time_max)

        call_kwargs = mock_list.call_args[1]
        assert "timeMin" in call_kwargs
        assert "timeMax" in call_kwargs

    @patch("gsuite_calendar.client.build")
    def test_get_events_parses_correctly(self, mock_build):
        """Test get_events returns Event objects."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "event1",
                    "summary": "Meeting",
                    "start": {"dateTime": "2026-01-28T10:00:00Z"},
                    "end": {"dateTime": "2026-01-28T11:00:00Z"},
                },
                {
                    "id": "event2",
                    "summary": "Lunch",
                    "start": {"date": "2026-01-28"},
                    "end": {"date": "2026-01-29"},
                },
            ]
        }
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        events = cal.get_events()

        assert len(events) == 2
        assert all(isinstance(e, Event) for e in events)
        assert events[0].summary == "Meeting"
        assert events[1].summary == "Lunch"
        assert events[1].all_day is True


class TestGetUpcoming:
    """Tests for get_upcoming method."""

    @patch.object(Calendar, "get_events")
    def test_get_upcoming_default(self, mock_get):
        """Test get_upcoming with default 7 days."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        mock_get.return_value = []
        cal.get_upcoming()

        call_kwargs = mock_get.call_args[1]
        time_min = call_kwargs["time_min"]
        time_max = call_kwargs["time_max"]

        # Should be roughly 7 days apart
        delta = time_max - time_min
        assert 6 < delta.days < 8

    @patch.object(Calendar, "get_events")
    def test_get_upcoming_custom_days(self, mock_get):
        """Test get_upcoming with custom days."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        mock_get.return_value = []
        cal.get_upcoming(days=14)

        call_kwargs = mock_get.call_args[1]
        time_min = call_kwargs["time_min"]
        time_max = call_kwargs["time_max"]

        delta = time_max - time_min
        assert 13 < delta.days < 15


class TestGetToday:
    """Tests for get_today method."""

    @patch.object(Calendar, "get_events")
    def test_get_today(self, mock_get):
        """Test get_today returns today's events."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        mock_get.return_value = []
        cal.get_today()

        call_kwargs = mock_get.call_args[1]
        time_min = call_kwargs["time_min"]
        time_max = call_kwargs["time_max"]

        # Should be exactly 1 day
        delta = time_max - time_min
        assert delta.days == 1


class TestGetCalendars:
    """Tests for get_calendars method."""

    @patch("gsuite_calendar.client.build")
    def test_get_calendars(self, mock_build):
        """Test get_calendars returns CalendarEntity objects."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.calendarList().list().execute.return_value = {
            "items": [
                {
                    "id": "primary",
                    "summary": "My Calendar",
                    "timeZone": "America/Buenos_Aires",
                    "primary": True,
                    "accessRole": "owner",
                },
                {
                    "id": "work@example.com",
                    "summary": "Work",
                    "accessRole": "reader",
                },
            ]
        }
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        calendars = cal.get_calendars()

        assert len(calendars) == 2
        assert all(isinstance(c, CalendarEntity) for c in calendars)
        assert calendars[0].primary is True
        assert calendars[1].summary == "Work"


class TestCreateEvent:
    """Tests for create_event method."""

    @patch("gsuite_calendar.client.build")
    def test_create_event_simple(self, mock_build):
        """Test creating a simple event."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().insert().execute.return_value = {
            "id": "new_event",
            "summary": "New Meeting",
            "start": {"dateTime": "2026-01-30T10:00:00Z"},
            "end": {"dateTime": "2026-01-30T11:00:00Z"},
        }
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        event = cal.create_event(
            summary="New Meeting",
            start=datetime(2026, 1, 30, 10, 0),
            end=datetime(2026, 1, 30, 11, 0),
        )

        assert isinstance(event, Event)
        assert event.id == "new_event"
        assert event.summary == "New Meeting"

        # Verify insert was called with correct body
        call_args = mock_service.events().insert.call_args
        body = call_args[1]["body"]
        assert body["summary"] == "New Meeting"

    @patch("gsuite_calendar.client.build")
    def test_create_event_all_day(self, mock_build):
        """Test creating an all-day event."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().insert().execute.return_value = {
            "id": "all_day",
            "summary": "Holiday",
            "start": {"date": "2026-01-30"},
            "end": {"date": "2026-01-31"},
        }
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        from datetime import date

        event = cal.create_event(
            summary="Holiday",
            start=date(2026, 1, 30),
            all_day=True,
        )

        # Verify date format (not dateTime)
        call_args = mock_service.events().insert.call_args
        body = call_args[1]["body"]
        assert "date" in body["start"]
        assert "dateTime" not in body["start"]

    @patch("gsuite_calendar.client.build")
    def test_create_event_with_attendees(self, mock_build):
        """Test creating event with attendees."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().insert().execute.return_value = {
            "id": "meeting",
            "summary": "Team Sync",
            "start": {"dateTime": "2026-01-30T10:00:00Z"},
            "end": {"dateTime": "2026-01-30T11:00:00Z"},
            "attendees": [
                {"email": "alice@example.com"},
                {"email": "bob@example.com"},
            ],
        }
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        cal.create_event(
            summary="Team Sync",
            start=datetime(2026, 1, 30, 10, 0),
            attendees=["alice@example.com", "bob@example.com"],
        )

        call_args = mock_service.events().insert.call_args
        body = call_args[1]["body"]
        assert len(body["attendees"]) == 2
        assert body["attendees"][0]["email"] == "alice@example.com"


class TestDeleteEvent:
    """Tests for delete_event method."""

    @patch("gsuite_calendar.client.build")
    def test_delete_event_success(self, mock_build):
        """Test successful event deletion."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        result = cal.delete_event("event123")

        assert result is True
        mock_service.events().delete.assert_called()

    @patch("gsuite_calendar.client.build")
    def test_delete_event_not_found(self, mock_build):
        """Test deletion of non-existent event."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.events().delete().execute.side_effect = Exception("Not found")
        mock_build.return_value = mock_service

        cal = Calendar(mock_auth)
        result = cal.delete_event("nonexistent")

        assert result is False


class TestParseEvent:
    """Tests for event parsing."""

    def test_parse_event_datetime(self):
        """Test parsing event with datetime."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        data = {
            "id": "event1",
            "summary": "Meeting",
            "description": "Weekly sync",
            "location": "Conference Room",
            "start": {"dateTime": "2026-01-28T10:00:00Z"},
            "end": {"dateTime": "2026-01-28T11:00:00Z"},
            "htmlLink": "https://calendar.google.com/event?id=123",
            "status": "confirmed",
        }

        event = cal._parse_event(data, "primary")

        assert event.id == "event1"
        assert event.summary == "Meeting"
        assert event.description == "Weekly sync"
        assert event.location == "Conference Room"
        assert event.all_day is False
        assert event.calendar_id == "primary"

    def test_parse_event_all_day(self):
        """Test parsing all-day event."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        data = {
            "id": "event2",
            "summary": "Holiday",
            "start": {"date": "2026-01-28"},
            "end": {"date": "2026-01-29"},
        }

        event = cal._parse_event(data, "primary")

        assert event.all_day is True

    def test_parse_event_with_attendees(self):
        """Test parsing event with attendees."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        data = {
            "id": "event3",
            "summary": "Team Meeting",
            "start": {"dateTime": "2026-01-28T10:00:00Z"},
            "end": {"dateTime": "2026-01-28T11:00:00Z"},
            "attendees": [
                {
                    "email": "alice@example.com",
                    "displayName": "Alice",
                    "responseStatus": "accepted",
                    "organizer": True,
                },
                {
                    "email": "bob@example.com",
                    "responseStatus": "needsAction",
                },
            ],
        }

        event = cal._parse_event(data, "primary")

        assert len(event.attendees) == 2
        assert event.attendees[0].email == "alice@example.com"
        assert event.attendees[0].organizer is True
        assert event.attendees[1].response_status == "needsAction"

    def test_parse_recurring_event(self):
        """Test parsing recurring event."""
        mock_auth = Mock()
        cal = Calendar(mock_auth)

        data = {
            "id": "event4",
            "summary": "Daily Standup",
            "start": {"dateTime": "2026-01-28T09:00:00Z"},
            "end": {"dateTime": "2026-01-28T09:15:00Z"},
            "recurringEventId": "recurring123",
            "recurrence": ["RRULE:FREQ=DAILY"],
        }

        event = cal._parse_event(data, "primary")

        assert event.recurring is True
        assert event.recurrence == ["RRULE:FREQ=DAILY"]
