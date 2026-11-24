"""Calendar notification channels: watch and stop (sync and async clients)."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from gsuite_calendar import AsyncCalendar, Calendar
from gsuite_core import Channel, Settings
from gsuite_core.exceptions import ValidationError

ADDRESS = "https://x.example/webhooks/calendar"
CREATED = {"id": "c1", "resourceId": "r1", "expiration": "1767225600000"}


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


@pytest.fixture
def service():
    with patch("gsuite_core.service.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture
def no_retries():
    s = Settings(max_retries=0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


class TestWatch:
    def test_watch(self, service):
        service.events().watch.return_value.execute.return_value = CREATED

        channel = Calendar(Mock()).watch(ADDRESS, "secret", channel_id="c1", ttl=600)

        assert (channel.id, channel.resource_id, channel.token) == ("c1", "r1", "secret")
        assert channel.expiration == datetime(2026, 1, 1, tzinfo=UTC)
        assert service.events().watch.call_args.kwargs == {
            "calendarId": "primary",
            "body": {
                "id": "c1",
                "type": "web_hook",
                "address": ADDRESS,
                "token": "secret",
                "params": {"ttl": "600"},
            },
        }

    def test_another_calendar(self, service):
        service.events().watch.return_value.execute.return_value = CREATED
        Calendar(Mock()).watch(ADDRESS, "secret", calendar_id="team@x.com")
        assert service.events().watch.call_args.kwargs["calendarId"] == "team@x.com"

    def test_insecure_address_never_reaches_google(self, service):
        with pytest.raises(ValidationError, match="address"):
            Calendar(Mock()).watch("http://x.example/hook", "secret")
        service.events().watch.assert_not_called()

    def test_stop(self, service):
        calendar = Calendar(Mock())
        calendar.stop_channel(Channel(id="c1", resource_id="r1"))
        calendar.stop_channel("c2", "r2")

        bodies = [call.kwargs["body"] for call in service.channels().stop.call_args_list]
        assert bodies == [{"id": "c1", "resourceId": "r1"}, {"id": "c2", "resourceId": "r2"}]


class TestAsyncWatch:
    async def test_watch_and_stop(self, no_retries):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.url.path, json.loads(request.content)))
            if request.url.path.endswith("/channels/stop"):
                return httpx.Response(204)
            return httpx.Response(200, json=CREATED)

        transport = httpx.MockTransport(handler)
        async with AsyncCalendar(FakeCredentials(), "team@x.com", transport=transport) as cal:
            channel = await cal.watch(ADDRESS, "secret", channel_id="c1")
            await cal.stop_channel(channel)

        assert (channel.resource_id, channel.token) == ("r1", "secret")
        (watch_path, watch_body), (stop_path, stop_body) = seen
        assert watch_path == "/calendar/v3/calendars/team@x.com/events/watch"
        assert watch_body == {
            "id": "c1",
            "type": "web_hook",
            "address": ADDRESS,
            "token": "secret",
        }
        assert stop_path == "/calendar/v3/channels/stop"
        assert stop_body == {"id": "c1", "resourceId": "r1"}
