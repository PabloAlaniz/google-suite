"""Incremental sync (history), ID-only listing and metadata format, sync and async."""

import json
from unittest.mock import MagicMock, Mock, patch

import httplib2
import httpx
import pytest
from googleapiclient.errors import HttpError

from gsuite_core import Settings
from gsuite_core.exceptions import SyncTokenExpiredError, ValidationError
from gsuite_gmail import AsyncGmail, Gmail
from gsuite_gmail._requests import add_history_page, finish_history
from gsuite_gmail.history import HistoryDelta

PAGE_1 = {
    "history": [
        {"id": "11", "messagesAdded": [{"message": {"id": "m1"}}, {"message": {"id": "m2"}}]},
        {"id": "12", "labelsAdded": [{"message": {"id": "m1"}, "labelIds": ["STARRED"]}]},
    ],
    "nextPageToken": "p2",
    "historyId": "15",
}
PAGE_2 = {
    "history": [
        {"id": "13", "messagesDeleted": [{"message": {"id": "m2"}}]},
        {"id": "14", "labelsRemoved": [{"message": {"id": "m3"}, "labelIds": ["UNREAD"]}]},
        {"id": "15", "messagesAdded": [{"message": {"id": "m1"}}]},  # repeated
    ],
    "historyId": "15",
}
HEADERS_ONLY = {
    "id": "m1",
    "threadId": "t1",
    "payload": {"headers": [{"name": "Subject", "value": "Hi"}, {"name": "From", "value": "a@x"}]},
}


def test_folding_drops_deleted_messages_and_repeats():
    delta = HistoryDelta()
    add_history_page(delta, PAGE_1)
    add_history_page(delta, PAGE_2)
    finish_history(delta)

    assert delta == HistoryDelta(
        added=["m1"], deleted=["m2"], labels_changed=["m1", "m3"], history_id="15"
    )


class TestSync:
    @pytest.fixture
    def service(self):
        with patch("gsuite_core.service.build") as build:
            svc = MagicMock()
            build.return_value = svc
            yield svc

    @pytest.fixture
    def gmail(self, service):
        return Gmail(Mock())

    def test_history_follows_pages(self, gmail, service):
        lister = service.users().history().list
        lister.return_value.execute.side_effect = [PAGE_1, PAGE_2]

        delta = gmail.history("10", history_types=["messageAdded", "messageDeleted"])

        assert (delta.added, delta.deleted, delta.history_id) == (["m1"], ["m2"], "15")
        first, second = (c.kwargs for c in lister.call_args_list[-2:])
        assert first["startHistoryId"] == "10"
        assert first["historyTypes"] == ["messageAdded", "messageDeleted"]
        assert second["pageToken"] == "p2"

    def test_expired_history_is_a_sync_token_error(self, gmail, service):
        error = HttpError(
            httplib2.Response({"status": 404}),
            json.dumps(
                {"error": {"code": 404, "message": "Requested entity was not found."}}
            ).encode(),
        )
        service.users().history().list.return_value.execute.side_effect = error

        with pytest.raises(SyncTokenExpiredError):
            gmail.history("1")

    def test_history_needs_a_start(self, gmail):
        with pytest.raises(ValidationError):
            gmail.history("")

    def test_ids_without_fetching(self, gmail, service):
        service.users().messages().list.return_value.execute.return_value = {
            "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t1"}]
        }

        assert list(gmail.iter_message_ids("from:ana", max_results=10)) == ["m1", "m2"]
        service.users().messages().get.assert_not_called()
        assert service.users().messages().list.call_args.kwargs["q"] == "from:ana"

    def test_history_id(self, gmail, service):
        service.users().getProfile.return_value.execute.return_value = {"historyId": 42}
        assert gmail.get_history_id() == "42"

    def test_thread_with_selected_headers(self, gmail, service):
        getter = service.users().threads().get
        getter.return_value.execute.return_value = {"id": "t1", "messages": [HEADERS_ONLY]}

        thread = gmail.get_thread("t1", format="metadata", headers=["From", "Subject"])

        assert getter.call_args.kwargs["format"] == "metadata"
        assert getter.call_args.kwargs["metadataHeaders"] == ["From", "Subject"]
        assert thread.messages[0].subject == "Hi"

    def test_headers_need_metadata_format(self, gmail):
        with pytest.raises(ValidationError, match="metadata"):
            gmail.get_message("m1", headers=["From"])


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


class TestAsync:
    @pytest.fixture(autouse=True)
    def settings(self):
        s = Settings(max_retries=0, _env_file=None)
        with patch("gsuite_core.config.get_settings", return_value=s):
            yield s

    @pytest.fixture
    def calls(self):
        return []

    @pytest.fixture
    async def gmail(self, calls):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path.removeprefix("/gmail/v1/users/me/")
            params = request.url.params
            calls.append((path, params))
            if path == "history":
                if params["startHistoryId"] == "old":
                    return httpx.Response(404, json={"error": {"code": 404, "message": "x"}})
                return httpx.Response(200, json=PAGE_2 if params.get("pageToken") else PAGE_1)
            if path == "messages":
                return httpx.Response(200, json={"messages": [{"id": "m1"}, {"id": "m2"}]})
            if path == "profile":
                return httpx.Response(200, json={"historyId": "99"})
            if path == "threads/t1":
                return httpx.Response(200, json={"id": "t1", "messages": [HEADERS_ONLY]})
            return httpx.Response(404, json={"error": {"code": 404}})

        async with AsyncGmail(FakeCredentials(), transport=httpx.MockTransport(handler)) as g:
            yield g

    async def test_history(self, gmail, calls):
        delta = await gmail.history("10", history_types=["messageAdded"])

        assert (delta.added, delta.deleted, delta.history_id) == (["m1"], ["m2"], "15")
        assert calls[0][1].get_list("historyTypes") == ["messageAdded"]
        assert calls[1][1]["pageToken"] == "p2"
        with pytest.raises(SyncTokenExpiredError):
            await gmail.history("old")

    async def test_ids_history_id_and_metadata_thread(self, gmail, calls):
        assert [i async for i in gmail.iter_message_ids(max_results=5)] == ["m1", "m2"]
        assert await gmail.get_history_id() == "99"

        thread = await gmail.get_thread("t1", format="metadata", headers=["Subject"])

        assert thread.messages[0].subject == "Hi"
        assert calls[-1][1]["format"] == "metadata"
        assert calls[-1][1].get_list("metadataHeaders") == ["Subject"]
