"""gsuite_core.aio.AsyncGoogleClient: auth, retries, errors and pagination."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from gsuite_core import Settings
from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.exceptions import (
    APIError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TokenRefreshError,
)

URL = "https://example.googleapis.com/v1/things"


class FakeCredentials:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.token = "t0"
        self.refreshes = 0

    def apply(self, headers):
        headers["authorization"] = f"Bearer {self.token}"

    def refresh(self, request):
        self.refreshes += 1
        self.token = f"t{self.refreshes}"
        self.valid = True


def error(status: int, reason: str | None = None, headers: dict | None = None) -> httpx.Response:
    body = {"error": {"code": status, "message": "nope"}}
    if reason:
        body["error"]["errors"] = [{"reason": reason}]
    return httpx.Response(status, json=body, headers=headers)


def client_with(responses, credentials=None):
    """An AsyncGoogleClient whose transport answers with ``responses`` in order."""
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    http = AsyncGoogleClient(
        credentials or FakeCredentials(), transport=httpx.MockTransport(handler)
    )
    return http, seen


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=3, retry_delay=1.0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


@pytest.fixture(autouse=True)
def no_sleep():
    async def instant(_):
        return None

    with patch("gsuite_core.aio.asyncio.sleep", side_effect=instant) as sleep:
        yield sleep


async def test_success_and_auth_header():
    http, seen = client_with([httpx.Response(200, json={"ok": 1})])
    assert await http.json("GET", URL, service="test", params={"q": "x"}) == {"ok": 1}
    assert seen[0].headers["authorization"] == "Bearer t0"
    assert seen[0].url.params["q"] == "x"


async def test_rate_limit_retried_for_post(no_sleep):
    http, seen = client_with(
        [error(429, headers={"retry-after": "4"}), httpx.Response(200, json={"id": "s"})]
    )
    assert await http.json("POST", URL, service="test", json={"a": 1}) == {"id": "s"}
    no_sleep.assert_called_once_with(4.0)
    assert json.loads(seen[1].content) == {"a": 1}


async def test_403_rate_limit_reason_retried():
    http, _ = client_with([error(403, "userRateLimitExceeded"), httpx.Response(200, json={})])
    assert await http.json("GET", URL, service="test") == {}


async def test_server_error_retried_only_for_idempotent():
    http, _ = client_with([error(503), httpx.Response(200, json={"ok": 1})])
    assert await http.json("GET", URL, service="test") == {"ok": 1}

    http, seen = client_with([error(500), httpx.Response(200, json={})])
    with pytest.raises(APIError) as exc_info:
        await http.json("POST", URL, service="test")
    assert exc_info.value.status_code == 500
    assert len(seen) == 1  # a POST that may have been applied is not repeated


async def test_network_error_retried_for_get_not_post():
    http, _ = client_with([httpx.ConnectTimeout("slow"), httpx.Response(200, json={"ok": 1})])
    assert await http.json("GET", URL, service="test") == {"ok": 1}

    http, _ = client_with([httpx.ConnectTimeout("slow")])
    with pytest.raises(httpx.ConnectTimeout):
        await http.json("POST", URL, service="test")


async def test_gives_up_after_max_retries(settings):
    http, seen = client_with([error(503)] * 10)
    with pytest.raises(APIError):
        await http.json("GET", URL, service="test")
    assert len(seen) == settings.max_retries + 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (error(404), NotFoundError),
        (error(403, "insufficientPermissions"), PermissionDeniedError),
        (error(403, "storageQuotaExceeded"), PermissionDeniedError),
    ],
)
async def test_errors_are_mapped(response, expected):
    http, _ = client_with([response])
    with pytest.raises(expected):
        await http.json("GET", URL, service="test", resource_type="thing", resource_id="x")


async def test_rate_limit_error_after_retries_carries_retry_after(settings):
    settings.max_retries = 0
    http, _ = client_with([error(429, headers={"retry-after": "9"})])
    with pytest.raises(RateLimitError) as exc_info:
        await http.json("GET", URL, service="test")
    assert exc_info.value.retry_after == 9


async def test_expired_token_refreshed_once_for_concurrent_requests():
    credentials = FakeCredentials(valid=False)
    http, seen = client_with([httpx.Response(200, json={})] * 5, credentials)

    await asyncio.gather(*(http.json("GET", URL, service="test") for _ in range(5)))

    assert credentials.refreshes == 1
    assert {r.headers["authorization"] for r in seen} == {"Bearer t1"}


async def test_google_auth_refresh_is_used():
    auth = MagicMock()
    auth.credentials = FakeCredentials(valid=False)
    auth.needs_refresh.return_value = True
    auth.refresh.side_effect = lambda: setattr(auth.credentials, "valid", True)
    http, _ = client_with([httpx.Response(200, json={})], auth)

    await http.json("GET", URL, service="test")

    auth.refresh.assert_called_once_with()  # persists the new token, unlike a bare refresh


async def test_refresh_failure():
    from google.auth.exceptions import RefreshError

    credentials = FakeCredentials(valid=False)
    credentials.refresh = MagicMock(side_effect=RefreshError("revoked"))
    http, _ = client_with([], credentials)
    with pytest.raises(TokenRefreshError):
        await http.json("GET", URL, service="test")


async def test_not_authenticated():
    auth = MagicMock(credentials=None)
    http, _ = client_with([], auth)
    with pytest.raises(NotAuthenticatedError):
        await http.json("GET", URL, service="test")


async def test_paginate():
    http, seen = client_with(
        [
            httpx.Response(200, json={"items": [{"id": 1}, {"id": 2}], "nextPageToken": "p2"}),
            httpx.Response(200, json={"items": [{"id": 3}]}),
        ]
    )

    items = [i async for i in http.paginate(URL, "items", service="test", params={"q": "x"})]

    assert [i["id"] for i in items] == [1, 2, 3]
    assert seen[1].url.params["pageToken"] == "p2"
    assert seen[1].url.params["q"] == "x"


async def test_paginate_max_items_shrinks_last_page():
    http, seen = client_with(
        [
            httpx.Response(
                200, json={"items": [{"id": i} for i in range(5)], "nextPageToken": "p2"}
            ),
            httpx.Response(200, json={"items": [{"id": 9}]}),
        ]
    )

    items = [
        i async for i in http.paginate(URL, "items", service="test", max_items=6, max_page_size=5)
    ]

    assert len(items) == 6
    assert [r.url.params["maxResults"] for r in seen] == ["5", "1"]


async def test_rate_limiter_is_awaited():
    calls = []

    class Limiter:
        async def acquire_async(self):
            calls.append(1)

    with patch("gsuite_core.aio.get_rate_limiter", return_value=Limiter()):
        http, _ = client_with([error(503), httpx.Response(200, json={})])
        await http.json("GET", URL, service="test")
    assert len(calls) == 2  # one token per attempt


async def test_context_manager_closes():
    async with AsyncGoogleClient(
        FakeCredentials(), transport=httpx.MockTransport(lambda r: httpx.Response(204))
    ) as http:
        assert await http.json("DELETE", URL, service="test") == {}
    assert http._client.is_closed
