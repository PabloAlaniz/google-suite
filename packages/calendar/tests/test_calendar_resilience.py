"""Timestamps, timezones, all-day events and pagination in the Calendar client."""

from datetime import UTC, date, datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_calendar.client import Calendar, _rfc3339
from gsuite_core import Settings


@pytest.fixture
def service():
    with patch("gsuite_calendar.client.build") as build:
        svc = MagicMock()
        svc.events().list().execute.return_value = {"items": []}
        build.return_value = svc
        yield svc


class TestRfc3339:
    def test_naive_is_utc(self):
        assert _rfc3339(datetime(2026, 1, 1, 10)) == "2026-01-01T10:00:00Z"

    def test_aware_utc(self):
        # Used to produce "2026-01-01T10:00:00+00:00Z", which the API rejects
        assert _rfc3339(datetime(2026, 1, 1, 10, tzinfo=UTC)) == "2026-01-01T10:00:00Z"

    def test_other_offset_is_converted(self):
        buenos_aires = timezone(timedelta(hours=-3))
        assert _rfc3339(datetime(2026, 1, 1, 7, tzinfo=buenos_aires)) == "2026-01-01T10:00:00Z"


def test_aware_range_is_sent_as_utc(service):
    start = datetime(2026, 5, 1, 9, tzinfo=timezone(timedelta(hours=-3)))

    Calendar(Mock()).get_events(time_min=start, time_max=start + timedelta(hours=1))

    params = service.events().list.call_args.kwargs
    assert params["timeMin"] == "2026-05-01T12:00:00Z"
    assert params["timeMax"] == "2026-05-01T13:00:00Z"


def test_today_uses_configured_timezone(service):
    settings = Settings(default_timezone="America/Argentina/Buenos_Aires", _env_file=None)
    with patch("gsuite_calendar.client.get_settings", return_value=settings):
        Calendar(Mock()).get_today()

    params = service.events().list.call_args.kwargs
    # Local midnight in Buenos Aires (UTC-3) is 03:00 UTC
    assert params["timeMin"].endswith("T03:00:00Z")
    assert params["timeMax"].endswith("T03:00:00Z")


def test_order_by_omitted_for_unexpanded_events(service):
    Calendar(Mock()).get_events(single_events=False)
    assert "orderBy" not in service.events().list.call_args.kwargs


def test_events_follow_pages(service):
    pages = iter(
        [
            {"items": [{"id": "1", "summary": "a"}], "nextPageToken": "p2"},
            {"items": [{"id": "2", "summary": "b"}]},
        ]
    )
    service.events().list.side_effect = lambda **kw: Mock(
        method="GET", execute=Mock(return_value=next(pages))
    )

    events = Calendar(Mock()).get_events(max_results=None)

    assert [e.id for e in events] == ["1", "2"]


class TestAllDay:
    def _body(self, service):
        return service.events().insert.call_args.kwargs["body"]

    def test_all_day_from_datetime_sends_a_date(self, service):
        service.events().insert().execute.return_value = {"id": "e", "summary": "x"}

        Calendar(Mock()).create_event("Off", start=datetime(2026, 2, 3, 15, 30), all_day=True)

        body = self._body(service)
        assert body["start"] == {"date": "2026-02-03"}
        assert body["end"] == {"date": "2026-02-04"}

    def test_all_day_from_date(self, service):
        service.events().insert().execute.return_value = {"id": "e", "summary": "x"}

        Calendar(Mock()).create_event("Off", start=date(2026, 2, 3), end=date(2026, 2, 5))

        assert self._body(service)["end"] == {"date": "2026-02-06"}


def test_get_event_other_errors_raise(service, http_error):
    from gsuite_core.exceptions import PermissionDeniedError

    service.events().get().execute.side_effect = http_error(403)
    with pytest.raises(PermissionDeniedError):
        Calendar(Mock()).get_event("e1")
