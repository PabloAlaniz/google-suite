"""Meet, recurrence, updates, quick add, instances and free/busy."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_calendar.client import Calendar
from gsuite_calendar.parser import CalendarParser
from gsuite_core.exceptions import ValidationError

EVENT = {
    "id": "e1",
    "summary": "Sync",
    "start": {
        "dateTime": "2026-03-01T10:00:00-03:00",
        "timeZone": "America/Argentina/Buenos_Aires",
    },
}


@pytest.fixture
def service():
    with patch("gsuite_calendar.client.build") as build:
        svc = MagicMock()
        for method in ("insert", "patch", "quickAdd"):
            getattr(svc.events(), method)().execute.return_value = EVENT
        build.return_value = svc
        yield svc


@pytest.fixture
def cal(service):
    return Calendar(Mock())


class TestCreate:
    def test_meet_link_requested(self, cal, service):
        cal.create_event("Sync", datetime(2026, 3, 1, 10), meet=True)

        kwargs = service.events().insert.call_args.kwargs
        request = kwargs["body"]["conferenceData"]["createRequest"]
        assert request["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
        assert len(request["requestId"]) == 32
        assert kwargs["conferenceDataVersion"] == 1

    def test_no_meet_by_default(self, cal, service):
        cal.create_event("Sync", datetime(2026, 3, 1, 10))
        kwargs = service.events().insert.call_args.kwargs
        assert "conferenceData" not in kwargs["body"]
        assert "conferenceDataVersion" not in kwargs

    def test_recurrence_attendees_and_notifications(self, cal, service):
        cal.create_event(
            "Standup",
            datetime(2026, 3, 2, 9),
            attendees=["a@x.com"],
            recurrence=["RRULE:FREQ=WEEKLY;BYDAY=MO"],
            send_updates="all",
        )

        kwargs = service.events().insert.call_args.kwargs
        assert kwargs["body"]["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]
        assert kwargs["body"]["attendees"] == [{"email": "a@x.com"}]
        # Invitations were never emailed before: sendUpdates wasn't set
        assert kwargs["sendUpdates"] == "all"

    def test_quick_add(self, cal, service):
        event = cal.quick_add("Lunch with Ana tomorrow at 1pm")
        assert event.id == "e1"
        assert (
            service.events().quickAdd.call_args.kwargs["text"] == "Lunch with Ana tomorrow at 1pm"
        )


class TestUpdate:
    def test_only_given_fields(self, cal, service):
        cal.update_event("e1", summary="New", send_updates="all")

        kwargs = service.events().patch.call_args.kwargs
        assert kwargs["body"] == {"summary": "New"}
        assert kwargs["sendUpdates"] == "all"

    def test_move_defaults_to_one_hour(self, cal, service):
        cal.update_event("e1", start=datetime(2026, 3, 1, 15))
        body = service.events().patch.call_args.kwargs["body"]
        assert body["start"]["dateTime"] == "2026-03-01T15:00:00"
        assert body["end"]["dateTime"] == "2026-03-01T16:00:00"

    def test_to_all_day(self, cal, service):
        cal.update_event("e1", start=date(2026, 3, 1), end=date(2026, 3, 2))
        body = service.events().patch.call_args.kwargs["body"]
        assert body["start"] == {"date": "2026-03-01"} and body["end"] == {"date": "2026-03-03"}

    def test_replaces_attendees(self, cal, service):
        cal.update_event("e1", attendees=[])
        assert service.events().patch.call_args.kwargs["body"] == {"attendees": []}

    def test_end_without_start(self, cal):
        with pytest.raises(ValidationError, match="start"):
            cal.update_event("e1", end=datetime(2026, 3, 1, 12))

    def test_nothing_to_update(self, cal):
        with pytest.raises(ValidationError):
            cal.update_event("e1")


def test_instances(cal, service):
    service.events().instances().execute.return_value = {"items": [EVENT, EVENT]}

    instances = cal.get_instances("e1", time_min=datetime(2026, 3, 1, tzinfo=UTC))

    assert len(instances) == 2
    assert service.events().instances.call_args.kwargs["timeMin"] == "2026-03-01T00:00:00Z"


def test_free_busy(cal, service):
    service.freebusy().query().execute.return_value = {
        "calendars": {
            "primary": {"busy": [{"start": "2026-03-01T13:00:00Z", "end": "2026-03-01T14:00:00Z"}]},
            "hidden@x.com": {"errors": [{"reason": "notFound"}], "busy": []},
        }
    }

    busy = cal.get_free_busy(
        datetime(2026, 3, 1, 9), datetime(2026, 3, 1, 18), calendars=["me", "hidden@x.com"]
    )

    assert busy == {
        "me": [
            {
                "start": datetime(2026, 3, 1, 13, tzinfo=UTC),
                "end": datetime(2026, 3, 1, 14, tzinfo=UTC),
            }
        ],
        "hidden@x.com": [],
    }
    items = service.freebusy().query.call_args.kwargs["body"]["items"]
    assert items == [{"id": "primary"}, {"id": "hidden@x.com"}]


def test_delete_notifies_when_asked(cal, service):
    cal.delete_event("e1", send_updates="all")
    assert service.events().delete.call_args.kwargs["sendUpdates"] == "all"


class TestParsing:
    def test_meet_link_from_conference_data(self):
        data = {
            **EVENT,
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "phone", "uri": "tel:1"},
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc"},
                ]
            },
        }
        assert (
            CalendarParser.parse_event(data, "primary").meet_link == "https://meet.google.com/abc"
        )

    def test_legacy_hangout_link(self):
        data = {**EVENT, "hangoutLink": "https://meet.google.com/old"}
        assert (
            CalendarParser.parse_event(data, "primary").meet_link == "https://meet.google.com/old"
        )

    def test_metadata(self):
        data = {
            **EVENT,
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-02T00:00:00Z",
            "creator": {"email": "ana@x.com"},
            "recurringEventId": "parent",
        }
        event = CalendarParser.parse_event(data, "primary")
        assert event.timezone == "America/Argentina/Buenos_Aires"
        assert event.created == datetime(2026, 1, 1, tzinfo=UTC)
        assert event.creator == "ana@x.com"
        assert event.recurring_event_id == "parent"
