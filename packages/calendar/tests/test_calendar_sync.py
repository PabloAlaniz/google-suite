"""Identification fields and incremental sync (sync and async clients)."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import httplib2
import httpx
import pytest
from googleapiclient.errors import HttpError

from gsuite_calendar import AsyncCalendar, Calendar
from gsuite_calendar.parser import CalendarParser
from gsuite_core import Settings
from gsuite_core.exceptions import SyncTokenExpiredError

INSTANCE = {
    "id": "abc_20260302T120000Z",
    "summary": "Standup",
    "iCalUID": "abc@google.com",
    "recurringEventId": "abc",
    "originalStartTime": {"dateTime": "2026-03-02T09:00:00-03:00"},
    "start": {"dateTime": "2026-03-02T10:00:00-03:00"},
    "organizer": {"email": "me@x.com", "displayName": "Me", "self": True},
    "attendees": [
        {"email": "room@resource.calendar.google.com", "resource": True},
        {"email": "ana@x.com", "displayName": "Ana", "responseStatus": "accepted"},
    ],
}
PAGE_1 = {"items": [INSTANCE], "nextPageToken": "p2"}
PAGE_2 = {"items": [{"id": "gone", "status": "cancelled"}], "nextSyncToken": "s2"}
GONE = {"error": {"code": 410, "errors": [{"reason": "fullSyncRequired"}], "message": "Gone"}}


def test_identification_fields():
    event = CalendarParser.parse_event(INSTANCE, "primary")

    assert event.ical_uid == "abc@google.com"
    assert event.original_start == datetime(2026, 3, 2, 12, tzinfo=UTC)
    assert (event.organizer_name, event.organizer_self) == ("Me", True)
    assert [a.resource for a in event.attendees] == [True, False]
    assert event.raw is INSTANCE


def test_all_day_original_start():
    event = CalendarParser.parse_event(
        {"id": "x", "originalStartTime": {"date": "2026-03-02"}, "start": {"date": "2026-03-03"}},
        "primary",
    )
    assert event.original_start.date().isoformat() == "2026-03-02"


class TestSync:
    @pytest.fixture
    def service(self):
        with patch("gsuite_core.service.build") as build:
            svc = MagicMock()
            build.return_value = svc
            yield svc

    def test_follows_pages_and_splits_cancelled(self, service):
        lister = service.events().list
        lister.return_value.execute.side_effect = [PAGE_1, PAGE_2]

        delta = Calendar(Mock()).sync("s1")

        assert [e.summary for e in delta.changed] == ["Standup"]
        assert [e.id for e in delta.cancelled] == ["gone"]
        assert delta.sync_token == "s2"
        first, second = (c.kwargs for c in lister.call_args_list[-2:])
        assert first == {
            "calendarId": "primary",
            "singleEvents": True,
            "maxResults": 2500,
            "syncToken": "s1",
        }  # no timeMin/orderBy: the API rejects them with a token
        assert second["pageToken"] == "p2"

    def test_invalidated_token(self, service):
        error = HttpError(httplib2.Response({"status": 410}), json.dumps(GONE).encode())
        service.events().list.return_value.execute.side_effect = error

        with pytest.raises(SyncTokenExpiredError):
            Calendar(Mock()).sync("old")


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


class TestAsyncSync:
    @pytest.fixture(autouse=True)
    def settings(self):
        s = Settings(max_retries=0, _env_file=None)
        with patch("gsuite_core.config.get_settings", return_value=s):
            yield s

    async def test_sync(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = request.url.params
            seen.append(params)
            if params.get("syncToken") == "old":
                return httpx.Response(410, json=GONE)
            return httpx.Response(200, json=PAGE_2 if params.get("pageToken") else PAGE_1)

        async with AsyncCalendar(FakeCredentials(), transport=httpx.MockTransport(handler)) as cal:
            delta = await cal.sync()
            with pytest.raises(SyncTokenExpiredError):
                await cal.sync("old")

        assert ([e.id for e in delta.cancelled], delta.sync_token) == (["gone"], "s2")
        assert "syncToken" not in seen[0]
        assert "timeMin" not in seen[0]
        assert seen[1]["pageToken"] == "p2"
