"""Gmail push notifications: watch and stop (sync and async clients)."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from gsuite_core import Settings
from gsuite_core.exceptions import ValidationError
from gsuite_gmail import AsyncGmail, Gmail, MailboxWatch

TOPIC = "projects/my-project/topics/gmail"
WATCHING = {"historyId": "9876", "expiration": "1767225600000"}


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
        service.users().watch.return_value.execute.return_value = WATCHING

        watch = Gmail(Mock()).watch(TOPIC)

        assert watch == MailboxWatch("9876", datetime(2026, 1, 1, tzinfo=UTC))
        assert service.users().watch.call_args.kwargs == {
            "userId": "me",
            "body": {"topicName": TOPIC},
        }

    def test_label_filter(self, service):
        service.users().watch.return_value.execute.return_value = WATCHING

        Gmail(Mock()).watch(TOPIC, label_ids=["INBOX"], label_filter="exclude")

        assert service.users().watch.call_args.kwargs["body"] == {
            "topicName": TOPIC,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "EXCLUDE",
        }

    @pytest.mark.parametrize("topic", ["gmail", "projects/p/topics/", "projects/p/subscriptions/s"])
    def test_topic_must_be_a_full_name(self, service, topic):
        with pytest.raises(ValidationError, match="topic"):
            Gmail(Mock()).watch(topic)
        service.users().watch.assert_not_called()

    def test_unknown_label_filter(self, service):
        with pytest.raises(ValidationError, match="label_filter"):
            Gmail(Mock()).watch(TOPIC, ["INBOX"], "only")

    def test_stop(self, service):
        Gmail(Mock()).stop_watch()
        service.users().stop.assert_called_once_with(userId="me")
        service.users().stop.return_value.execute.assert_called_once()


class TestAsyncWatch:
    async def test_watch_and_stop(self, no_retries):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path, request.content))
            if request.url.path.endswith("/stop"):
                return httpx.Response(204)
            return httpx.Response(200, json=WATCHING)

        async with AsyncGmail(FakeCredentials(), transport=httpx.MockTransport(handler)) as gmail:
            watch = await gmail.watch(TOPIC, ["INBOX"])
            await gmail.stop_watch()

        assert watch.history_id == "9876"
        assert watch.expiration == datetime(2026, 1, 1, tzinfo=UTC)
        (method, path, body), (stop_method, stop_path, _) = seen
        assert (method, path) == ("POST", "/gmail/v1/users/me/watch")
        assert json.loads(body) == {
            "topicName": TOPIC,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        }
        assert (stop_method, stop_path) == ("POST", "/gmail/v1/users/me/stop")
