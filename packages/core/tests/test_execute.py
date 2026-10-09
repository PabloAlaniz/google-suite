"""execute(), paginate(), backoff and transport timeouts."""

import json
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from gsuite_core import Settings, authorized_http, execute, map_http_error, paginate
from gsuite_core.api_utils import MAX_BACKOFF, MAX_RETRY_AFTER, _backoff
from gsuite_core.exceptions import (
    APIError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
)


def http_error(status: int, reason: str | None = None, retry_after: str | None = None) -> HttpError:
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    body = {"error": {"code": status, "message": "x"}}
    if reason:
        body["error"]["errors"] = [{"reason": reason}]
    return HttpError(httplib2.Response(headers), json.dumps(body).encode())


def request(method: str, *outcomes):
    """A fake googleapiclient request whose execute() yields outcomes in order."""
    req = MagicMock()
    req.method = method
    req.execute.side_effect = list(outcomes)
    return req


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=3, retry_delay=1.0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


@pytest.fixture
def sleep():
    with patch("gsuite_core.api_utils.time.sleep") as mock_sleep:
        yield mock_sleep


class TestMapHttpErrorReasons:
    def test_403_rate_limit_reason_is_rate_limit(self):
        assert isinstance(
            map_http_error(http_error(403, "userRateLimitExceeded"), "gmail"), RateLimitError
        )

    def test_403_quota_reason(self):
        assert isinstance(
            map_http_error(http_error(403, "dailyLimitExceeded"), "gmail"), QuotaExceededError
        )

    def test_storage_quota_is_not_api_quota(self):
        # A full Drive mentions "quota" but retrying or backing off won't help
        error = map_http_error(http_error(403, "storageQuotaExceeded"), "drive")
        assert isinstance(error, PermissionDeniedError)

    def test_403_other_reason_is_permission_denied(self):
        assert isinstance(
            map_http_error(http_error(403, "insufficientPermissions"), "gmail"),
            PermissionDeniedError,
        )

    def test_404_carries_resource(self):
        error = map_http_error(http_error(404), "drive", "file", "abc")
        assert isinstance(error, NotFoundError)
        assert (error.resource_type, error.resource_id) == ("file", "abc")

    def test_429_retry_after(self):
        assert map_http_error(http_error(429, retry_after="7"), "gmail").retry_after == 7

    def test_retry_after_http_date_is_ignored(self):
        error = http_error(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")
        assert map_http_error(error, "gmail").retry_after is None


class TestExecute:
    def test_success(self, sleep):
        assert execute(request("GET", {"ok": 1}), "gmail") == {"ok": 1}
        sleep.assert_not_called()

    def test_rate_limit_retried_even_for_post(self, sleep):
        req = request("POST", http_error(429), {"id": "sent"})
        assert execute(req, "gmail") == {"id": "sent"}
        assert req.execute.call_count == 2

    def test_403_rate_limit_retried(self, sleep):
        req = request("GET", http_error(403, "rateLimitExceeded"), {"ok": 1})
        assert execute(req, "gmail") == {"ok": 1}

    def test_server_error_retried_for_get(self, sleep):
        req = request("GET", http_error(503), http_error(500), {"ok": 1})
        assert execute(req, "gmail") == {"ok": 1}
        assert sleep.call_count == 2

    def test_server_error_not_retried_for_post(self, sleep):
        # The send may have happened; retrying could deliver the email twice
        req = request("POST", http_error(500), {"id": "dup"})
        with pytest.raises(APIError):
            execute(req, "gmail")
        assert req.execute.call_count == 1

    def test_network_error_retried_for_get(self, sleep):
        req = request("GET", TimeoutError(), ConnectionResetError(), {"ok": 1})
        assert execute(req, "gmail") == {"ok": 1}

    def test_network_error_not_retried_for_post(self, sleep):
        req = request("POST", TimeoutError())
        with pytest.raises(TimeoutError):
            execute(req, "gmail")
        sleep.assert_not_called()

    def test_client_error_not_retried(self, sleep):
        req = request("GET", http_error(404))
        with pytest.raises(NotFoundError):
            execute(req, "drive", "file", "abc")
        sleep.assert_not_called()

    def test_gives_up_after_max_retries(self, sleep, settings):
        req = request("GET", *[http_error(503)] * 10)
        with pytest.raises(APIError) as exc_info:
            execute(req, "gmail")
        assert req.execute.call_count == settings.max_retries + 1
        assert exc_info.value.status_code == 503

    def test_rate_limit_not_retried_when_disabled(self, sleep, settings):
        settings.retry_on_rate_limit = False
        req = request("GET", http_error(429))
        with pytest.raises(RateLimitError):
            execute(req, "gmail")
        sleep.assert_not_called()

    def test_honors_retry_after(self, sleep):
        execute(request("GET", http_error(429, retry_after="5"), {}), "gmail")
        sleep.assert_called_once_with(5.0)

    def test_mapped_error_keeps_cause(self, sleep):
        original = http_error(404)
        with pytest.raises(NotFoundError) as exc_info:
            execute(request("GET", original), "gmail")
        assert exc_info.value.__cause__ is original


class TestBackoff:
    def test_full_jitter_bounds(self):
        with patch("gsuite_core.api_utils.random.uniform", side_effect=lambda a, b: b) as uniform:
            assert _backoff(0, 1.0) == 1.0
            assert _backoff(3, 1.0) == 8.0
            assert _backoff(20, 1.0) == MAX_BACKOFF
        assert uniform.call_args.args[0] == 0

    def test_retry_after_is_capped(self):
        assert _backoff(0, 1.0, retry_after=3600) == MAX_RETRY_AFTER


class TestPaginate:
    def _list_method(self, pages):
        responses = iter(pages)
        method = MagicMock(side_effect=lambda **params: request("GET", next(responses)))
        return method

    def test_follows_page_tokens(self):
        method = self._list_method(
            [
                {"files": [{"id": 1}, {"id": 2}], "nextPageToken": "p2"},
                {"files": [{"id": 3}]},
            ]
        )

        items = list(paginate(method, "files", "drive", page_size_param="pageSize", q="x"))

        assert [i["id"] for i in items] == [1, 2, 3]
        first, second = (c.kwargs for c in method.call_args_list)
        assert first == {"q": "x", "pageSize": 100}
        assert second == {"q": "x", "pageSize": 100, "pageToken": "p2"}

    def test_stops_at_max_items_and_shrinks_page(self):
        method = self._list_method(
            [
                {"messages": [{"id": i} for i in range(5)], "nextPageToken": "p2"},
                {"messages": [{"id": i} for i in range(5, 10)], "nextPageToken": "p3"},
            ]
        )

        items = list(paginate(method, "messages", "gmail", max_items=7, max_page_size=5))

        assert len(items) == 7
        assert [c.kwargs["maxResults"] for c in method.call_args_list] == [5, 2]

    def test_is_lazy(self):
        method = self._list_method([{"items": [{"id": 1}], "nextPageToken": "p2"}])
        iterator = paginate(method, "items", "calendar")
        assert next(iterator) == {"id": 1}
        assert method.call_count == 1

    def test_empty_response(self):
        method = self._list_method([{}])
        assert list(paginate(method, "items", "calendar")) == []


def test_authorized_http_sets_timeout(settings):
    settings.request_timeout = 12
    http = authorized_http(credentials=MagicMock())
    assert http.http.timeout == 12
    assert authorized_http(MagicMock(), timeout=3).http.timeout == 3


class FakeBatch:
    """Stands in for BatchHttpRequest: runs callbacks with canned outcomes."""

    def __init__(self, outcomes, callback):
        self.outcomes = outcomes
        self.callback = callback
        self.items = []

    def add(self, request, request_id):
        self.items.append((request, request_id))

    def execute(self):
        for request, request_id in self.items:
            outcome = self.outcomes[request]
            if isinstance(outcome, Exception):
                self.callback(request_id, None, outcome)
            else:
                self.callback(request_id, outcome, None)


class TestExecuteBatch:
    def _service(self, outcomes):
        service = MagicMock()
        batches = []

        def new_batch(callback):
            batch = FakeBatch(outcomes, callback)
            batches.append(batch)
            return batch

        service.new_batch_http_request.side_effect = new_batch
        return service, batches

    def test_results_in_order_and_chunked(self, sleep):
        from gsuite_core import execute_batch

        reqs = [f"r{i}" for i in range(5)]
        service, batches = self._service({r: {"id": r} for r in reqs})

        results = execute_batch(service, reqs, "gmail", batch_size=2)

        assert [r["id"] for r in results] == reqs
        assert [len(b.items) for b in batches] == [2, 2, 1]

    def test_errors_are_returned_in_place(self, sleep):
        from gsuite_core import execute_batch

        service, _ = self._service({"ok": {"id": 1}, "gone": http_error(404)})

        ok, gone = execute_batch(service, ["ok", "gone"], "gmail", "message")

        assert ok == {"id": 1}
        assert isinstance(gone, NotFoundError)

    def test_rate_limited_items_are_retried_individually(self, sleep):
        from gsuite_core import execute_batch

        retried = request("GET", {"id": "late"})
        service, _ = self._service({"ok": {"id": 1}, retried: http_error(429)})

        assert execute_batch(service, ["ok", retried], "gmail") == [{"id": 1}, {"id": "late"}]

    def test_empty(self):
        from gsuite_core import execute_batch

        service = MagicMock()
        assert execute_batch(service, [], "gmail") == []
        service.new_batch_http_request.assert_not_called()


class TestRateLimit:
    def test_bucket_allows_burst_then_waits(self):
        from gsuite_core.rate_limit import TokenBucket

        bucket = TokenBucket(rate=2, burst=2)
        assert bucket._take() == 0 and bucket._take() == 0
        assert 0 < bucket._take() <= 0.5

    def test_invalid_rate(self):
        from gsuite_core.rate_limit import TokenBucket

        with pytest.raises(ValueError):
            TokenBucket(0)

    def test_execute_acquires_a_token_per_attempt(self, settings, sleep):
        limiter = MagicMock()
        with patch("gsuite_core.api_utils.get_rate_limiter", return_value=limiter):
            execute(request("GET", http_error(503), {"ok": 1}), "gmail")
        assert limiter.acquire.call_count == 2

    def test_off_by_default(self, settings):
        from gsuite_core.rate_limit import get_rate_limiter

        assert get_rate_limiter() is None

    def test_async_acquire(self):
        import asyncio

        from gsuite_core.rate_limit import TokenBucket

        bucket = TokenBucket(rate=1000, burst=1)
        asyncio.run(bucket.acquire_async())
        asyncio.run(bucket.acquire_async())  # waits ~1 ms for the refill
