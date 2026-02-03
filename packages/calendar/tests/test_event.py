"""Tests for Calendar Event entity."""

from datetime import datetime

import pytest

from gsuite_calendar.event import Attendee, Event


class TestEvent:
    """Tests for Event entity."""

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return Event(
            id="event123",
            summary="Team Meeting",
            description="Weekly sync",
            location="Conference Room A",
            start=datetime(2026, 1, 30, 10, 0, 0),
            end=datetime(2026, 1, 30, 11, 0, 0),
            all_day=False,
            attendees=[
                Attendee(email="alice@example.com", name="Alice"),
                Attendee(email="bob@example.com", name="Bob"),
            ],
        )

    def test_duration_minutes(self, sample_event):
        """Test duration calculation."""
        assert sample_event.duration_minutes == 60

    def test_duration_minutes_none(self):
        """Test duration when times not set."""
        event = Event(id="1", summary="Test")
        assert event.duration_minutes is None

    def test_is_all_day(self, sample_event):
        """Test is_all_day property."""
        assert sample_event.is_all_day is False

        all_day_event = Event(id="2", summary="Holiday", all_day=True)
        assert all_day_event.is_all_day is True

    def test_is_recurring(self, sample_event):
        """Test is_recurring property."""
        assert sample_event.is_recurring is False

        recurring_event = Event(
            id="3",
            summary="Daily Standup",
            recurring=True,
            recurrence=["RRULE:FREQ=DAILY"],
        )
        assert recurring_event.is_recurring is True


class TestAttendee:
    """Tests for Attendee entity."""

    def test_attendee_creation(self):
        """Test creating an attendee."""
        att = Attendee(
            email="user@example.com",
            name="Test User",
            response_status="accepted",
        )

        assert att.email == "user@example.com"
        assert att.name == "Test User"
        assert att.response_status == "accepted"

    def test_attendee_defaults(self):
        """Test attendee default values."""
        att = Attendee(email="user@example.com")

        assert att.name is None
        assert att.response_status == "needsAction"
        assert att.organizer is False
        assert att.self_ is False
