"""Drive incremental sync and notification channels (sync and async clients)."""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from gsuite_core import Channel, Settings
from gsuite_core.exceptions import ValidationError
from gsuite_drive import AsyncDrive, Drive

ADDRESS = "https://x.example/webhooks/drive"
PAGE_1 = {
    "nextPageToken": "p2",
    "changes": [
        {"fileId": "f1", "file": {"id": "f1", "name": "Budget", "mimeType": "text/plain"}},
        {"fileId": "f2", "removed": True},
    ],
}
PAGE_2 = {
    "newStartPageToken": "t9",
    "changes": [
        {"fileId": "f3", "file": {"id": "f3", "name": "Old", "trashed": True}},
        {"fileId": "f4"},  # no access any more: Drive sends no file
        {"driveId": "d1", "changeType": "drive"},  # a shared drive, not a file
    ],
}
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


class TestChanges:
    def test_start_page_token(self, service):
        service.changes().getStartPageToken.return_value.execute.return_value = {
            "startPageToken": 42
        }
        assert Drive(Mock()).get_start_page_token() == "42"
        service.changes().getStartPageToken.assert_called_with(supportsAllDrives=True)

    def test_follows_pages_and_splits_removed(self, service):
        lister = service.changes().list
        lister.return_value.execute.side_effect = [PAGE_1, PAGE_2]
        drive = Drive(Mock())

        delta = drive.changes("t1")

        assert [(f.id, f.name, f.trashed) for f in delta.changed] == [
            ("f1", "Budget", False),
            ("f3", "Old", True),
        ]
        assert delta.changed[0]._drive is drive
        assert delta.removed == ["f2", "f4"]
        assert delta.page_token == "t9"
        first, second = (call.kwargs for call in lister.call_args_list[-2:])
        assert first["pageToken"] == "t1"
        assert first["includeRemoved"] is True
        assert first["supportsAllDrives"] is True
        assert "newStartPageToken" in first["fields"]
        assert second["pageToken"] == "p2"

    def test_page_token_is_required(self, service):
        with pytest.raises(ValidationError, match="page_token"):
            Drive(Mock()).changes(" ")


class TestWatchChanges:
    def test_watch_from_a_token(self, service):
        service.changes().watch.return_value.execute.return_value = CREATED

        channel = Drive(Mock()).watch_changes(ADDRESS, "secret", page_token="t1", channel_id="c1")

        assert (channel.id, channel.resource_id, channel.token) == ("c1", "r1", "secret")
        kwargs = service.changes().watch.call_args.kwargs
        assert kwargs["pageToken"] == "t1"
        assert kwargs["supportsAllDrives"] is True
        assert kwargs["body"] == {
            "id": "c1",
            "type": "web_hook",
            "address": ADDRESS,
            "token": "secret",
        }

    def test_watch_from_now(self, service):
        service.changes().getStartPageToken.return_value.execute.return_value = {
            "startPageToken": "42"
        }
        service.changes().watch.return_value.execute.return_value = CREATED

        Drive(Mock()).watch_changes(ADDRESS, "secret")

        assert service.changes().watch.call_args.kwargs["pageToken"] == "42"

    def test_token_is_required(self, service):
        with pytest.raises(ValidationError, match="token"):
            Drive(Mock()).watch_changes(ADDRESS, "")
        service.changes().watch.assert_not_called()

    def test_stop(self, service):
        Drive(Mock()).stop_channel(Channel(id="c1", resource_id="r1"))
        assert service.channels().stop.call_args.kwargs == {
            "body": {"id": "c1", "resourceId": "r1"}
        }


class TestAsync:
    async def test_changes_watch_and_stop(self, no_retries):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            path, params = request.url.path, request.url.params
            seen.append((request.method, path, params, request.content))
            if path.endswith("/changes/startPageToken"):
                return httpx.Response(200, json={"startPageToken": "42"})
            if path.endswith("/changes/watch"):
                return httpx.Response(200, json=CREATED)
            if path.endswith("/channels/stop"):
                return httpx.Response(204)
            return httpx.Response(200, json=PAGE_2 if params["pageToken"] == "p2" else PAGE_1)

        async with AsyncDrive(FakeCredentials(), transport=httpx.MockTransport(handler)) as drive:
            delta = await drive.changes("t1")
            channel = await drive.watch_changes(ADDRESS, "secret", channel_id="c1")
            await drive.stop_channel(channel)
            with pytest.raises(TypeError, match="AsyncDrive"):
                delta.changed[0].trash()

        assert [f.id for f in delta.changed] == ["f1", "f3"]
        assert (delta.removed, delta.page_token) == (["f2", "f4"], "t9")
        assert [(method, path) for method, path, _, _ in seen] == [
            ("GET", "/drive/v3/changes"),
            ("GET", "/drive/v3/changes"),
            ("GET", "/drive/v3/changes/startPageToken"),
            ("POST", "/drive/v3/changes/watch"),
            ("POST", "/drive/v3/channels/stop"),
        ]
        watch = seen[3]
        assert watch[2]["pageToken"] == "42"
        assert json.loads(watch[3])["token"] == "secret"
        assert json.loads(seen[4][3]) == {"id": "c1", "resourceId": "r1"}
