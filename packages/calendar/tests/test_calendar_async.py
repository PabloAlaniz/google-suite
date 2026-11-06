"""AsyncCalendar against a fake Calendar REST API (httpx.MockTransport)."""

import json
import logging
from datetime import UTC, date, datetime
from unittest.mock import patch

import httpx
import pytest

from gsuite_calendar import AsyncCalendar, Event
from gsuite_core import Settings
from gsuite_core.exceptions import ValidationError

PREFIX = "/calendar/v3/"


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


def raw_event(eid="e1", summary="Standup", **extra):
    return {
        "id": eid,
        "summary": summary,
        "start": {"dateTime": "2026-03-02T09:00:00Z"},
        "end": {"dateTime": "2026-03-02T09:30:00Z"},
        **extra,
    }


class FakeCalendarApi:
    """Answers from ``responses`` keyed by (method, path); records every request."""

    def __init__(self):
        self.calls = []
        self.responses = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode().split("?")[0].removeprefix(PREFIX)
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, dict(request.url.params), body))
        answer = self.responses.get((request.method, path))
        if callable(answer):
            answer = answer(request)
        if answer is None:
            return httpx.Response(404, json={"error": {"code": 404, "message": "not found"}})
        status, payload = answer
        return httpx.Response(status, json=payload)

    def last(self):
        return self.calls[-1]


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=0, default_timezone="America/Argentina/Buenos_Aires", _env_file=None)
    with (
        patch("gsuite_core.config.get_settings", return_value=s),
        patch("gsuite_calendar._requests.get_settings", return_value=s),
    ):
        yield s


@pytest.fixture
def api():
    return FakeCalendarApi()


@pytest.fixture
async def cal(api):
    transport = httpx.MockTransport(api.handler)
    async with AsyncCalendar(FakeCredentials(), transport=transport) as client:
        yield client


class TestReading:
    async def test_events_follow_pages_with_the_sync_parameters(self, cal, api):
        def page(request):
            if request.url.params.get("pageToken") == "p2":
                return 200, {"items": [raw_event("e2", "Retro")]}
            return 200, {"items": [raw_event()], "nextPageToken": "p2"}

        api.responses["GET", "calendars/primary/events"] = page

        events = await cal.get_events(time_min=datetime(2026, 3, 1), max_results=None)

        assert [e.summary for e in events] == ["Standup", "Retro"]
        assert all(isinstance(e, Event) for e in events)
        _, _, params, _ = api.calls[0]
        assert params["timeMin"] == "2026-03-01T00:00:00Z"
        assert (params["singleEvents"], params["orderBy"]) == ("true", "startTime")

    async def test_calendar_ids_are_escaped_in_the_path(self, cal, api):
        holidays = "en.usa#holiday@group.v.calendar.google.com"
        api.responses["GET", "calendars/en.usa%23holiday%40group.v.calendar.google.com/events"] = (
            200,
            {"items": [raw_event()]},
        )

        (event,) = await cal.get_events(calendar_id=holidays)

        assert event.calendar_id == holidays

    async def test_get_event_none_when_missing(self, cal, api):
        api.responses["GET", "calendars/primary/events/e1"] = (200, raw_event())

        assert (await cal.get_event("e1")).id == "e1"
        assert await cal.get_event("nope") is None

    async def test_calendars_and_instances(self, cal, api):
        api.responses["GET", "users/me/calendarList"] = (
            200,
            {"items": [{"id": "primary", "summary": "Me"}]},
        )
        api.responses["GET", "calendars/primary/events/e1/instances"] = (
            200,
            {"items": [raw_event("e1_1")]},
        )

        assert [c.summary for c in await cal.get_calendars()] == ["Me"]
        (instance,) = await cal.get_instances("e1", time_max=datetime(2026, 4, 1, tzinfo=UTC))
        assert instance.id == "e1_1"
        assert api.last()[2]["timeMax"] == "2026-04-01T00:00:00Z"

    async def test_free_busy_answers_with_the_names_asked(self, cal, api, caplog):
        api.responses["POST", "freeBusy"] = (
            200,
            {
                "calendars": {
                    "primary": {
                        "busy": [{"start": "2026-03-02T09:00:00Z", "end": "2026-03-02T10:00:00Z"}]
                    },
                    "x@example.com": {"errors": [{"reason": "notFound"}]},
                }
            },
        )

        with caplog.at_level(logging.WARNING, "gsuite_calendar.client"):
            busy = await cal.get_free_busy(
                datetime(2026, 3, 2), datetime(2026, 3, 3), ["me", "x@example.com"]
            )

        assert busy["me"][0]["start"] == datetime(2026, 3, 2, 9, tzinfo=UTC)
        assert busy["x@example.com"] == []
        assert [i["id"] for i in api.last()[3]["items"]] == ["primary", "x@example.com"]
        assert "x@example.com" in caplog.text


class TestWriting:
    async def test_create_with_attendees_and_meet(self, cal, api):
        api.responses["POST", "calendars/primary/events"] = (200, raw_event())

        await cal.create_event(
            "Standup",
            datetime(2026, 3, 2, 9),
            attendees=["ana@example.com"],
            meet=True,
            send_updates="all",
        )

        _, _, params, body = api.last()
        assert params == {"sendUpdates": "all", "conferenceDataVersion": "1"}
        assert body["start"] == {
            "dateTime": "2026-03-02T09:00:00",
            "timeZone": "America/Argentina/Buenos_Aires",
        }
        assert body["end"]["dateTime"] == "2026-03-02T10:00:00"
        assert body["attendees"] == [{"email": "ana@example.com"}]
        assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {
            "type": "hangoutsMeet"
        }
        assert "description" not in body

    async def test_all_day_end_is_exclusive(self, cal, api):
        api.responses["POST", "calendars/primary/events"] = (200, raw_event())

        await cal.create_event("Trip", date(2026, 3, 2), date(2026, 3, 4))

        body = api.last()[3]
        assert (body["start"], body["end"]) == ({"date": "2026-03-02"}, {"date": "2026-03-05"})

    async def test_quick_add(self, cal, api):
        api.responses["POST", "calendars/primary/events/quickAdd"] = (200, raw_event())

        await cal.quick_add("Lunch tomorrow at 1pm")

        assert api.last()[2] == {"text": "Lunch tomorrow at 1pm", "sendUpdates": "none"}

    async def test_update_sends_only_what_changes(self, cal, api):
        api.responses["PATCH", "calendars/primary/events/e1"] = (200, raw_event())

        await cal.update_event("e1", location="Room 2", attendees=[])

        assert api.last()[3] == {"location": "Room 2", "attendees": []}

    async def test_update_rejects_end_without_start_before_any_request(self, cal, api):
        with pytest.raises(ValidationError, match="start"):
            await cal.update_event("e1", end=datetime(2026, 3, 2, 10))

        assert api.calls == []

    async def test_delete(self, cal, api):
        api.responses["DELETE", "calendars/primary/events/e1"] = (204, None)

        assert await cal.delete_event("e1", send_updates="all") is True
        assert api.last()[2] == {"sendUpdates": "all"}
        assert await cal.delete_event("nope") is False
