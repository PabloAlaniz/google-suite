"""Pagination, not-found and retry behavior of the Gmail client."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_gmail.client import Gmail

RAW = {"id": "m", "threadId": "t", "payload": {"headers": []}, "labelIds": []}


@pytest.fixture
def service():
    with patch("gsuite_gmail.client.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("gsuite_core.api_utils.time.sleep"):
        yield


def _pages(service, *pages):
    responses = iter(pages)
    service.users().messages().list.side_effect = lambda **kw: Mock(
        method="GET", execute=Mock(return_value=next(responses))
    )


def test_messages_follow_pages(service):
    _pages(
        service,
        {"messages": [{"id": "1"}, {"id": "2"}], "nextPageToken": "p2"},
        {"messages": [{"id": "3"}]},
    )
    service.users().messages().get().execute.side_effect = lambda: dict(RAW)

    messages = Gmail(Mock()).get_messages(query="is:unread", max_results=None)

    assert len(messages) == 3
    tokens = [c.kwargs.get("pageToken") for c in service.users().messages().list.call_args_list]
    assert tokens == [None, "p2"]


def test_max_results_above_500_spans_pages(service):
    _pages(
        service,
        {"messages": [{"id": str(i)} for i in range(500)], "nextPageToken": "p2"},
        {"messages": [{"id": str(i)} for i in range(500, 1000)]},
    )
    service.users().messages().get().execute.side_effect = lambda: dict(RAW)

    messages = Gmail(Mock()).get_messages(max_results=600, include_body=False)

    # Used to be silently capped at 500
    assert len(messages) == 600
    sizes = [c.kwargs["maxResults"] for c in service.users().messages().list.call_args_list]
    assert sizes == [500, 100]


def test_iter_messages_is_lazy(service):
    _pages(service, {"messages": [{"id": "1"}, {"id": "2"}]})
    service.users().messages().get().execute.side_effect = lambda: dict(RAW)
    get = service.users().messages().get
    get.reset_mock()

    first = next(Gmail(Mock()).iter_messages(max_results=None))

    assert first.id == "m"
    assert get.call_count == 1


def test_get_message_returns_none_when_missing(service, http_error):
    service.users().messages().get().execute.side_effect = http_error(404)
    assert Gmail(Mock()).get_message("gone") is None


def test_get_thread_returns_none_when_missing(service, http_error):
    service.users().threads().get().execute.side_effect = http_error(404)
    assert Gmail(Mock()).get_thread("gone") is None


def test_rate_limited_read_is_retried(service, http_error):
    service.users().getProfile().method = "GET"
    service.users().getProfile().execute.side_effect = [
        http_error(429),
        http_error(403, "userRateLimitExceeded"),
        {"emailAddress": "me@example.com"},
    ]

    assert Gmail(Mock()).get_profile() == {"emailAddress": "me@example.com"}


def test_send_is_not_retried_on_server_error(service, http_error):
    from gsuite_core.exceptions import APIError

    send = service.users().messages().send()
    send.method = "POST"
    send.execute.side_effect = [http_error(500), {"id": "dup"}]

    with pytest.raises(APIError):
        Gmail(Mock()).send(to=["a@example.com"], subject="s", body="b")
    assert send.execute.call_count == 1
