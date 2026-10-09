"""Async foundation for the suite: an httpx client with Google auth and the sync policies.

googleapiclient is synchronous, so async clients call the REST APIs directly
through ``AsyncGoogleClient``. Everything that makes the sync path robust
applies here too, from the same code:

- the retry decision and error mapping of ``gsuite_core.api_utils``
  (rate limits retried for any method; 5xx and network errors only for
  idempotent ones; Retry-After honored; errors raised as GSuiteError types),
- the process-wide token bucket (GSUITE_RATE_LIMIT),
- GSUITE_REQUEST_TIMEOUT / GSUITE_MAX_RETRIES / GSUITE_RETRY_DELAY.

Requires ``pip install "gsuite-sdk[async]"`` (httpx).

Example:
    async with AsyncGoogleClient(auth) as http:
        profile = await http.json("GET", f"{GMAIL}/users/me/profile", service="gmail")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from gsuite_core.api_utils import (
    _backoff,
    error_for_status,
    parse_retry_after,
    reason_from_body,
    should_retry_status,
)
from gsuite_core.exceptions import ConfigurationError, NotAuthenticatedError, TokenRefreshError
from gsuite_core.rate_limit import get_rate_limiter

logger = logging.getLogger(__name__)

HTTPX_MISSING = 'Async support needs httpx: pip install "gsuite-sdk[async]"'


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise ConfigurationError(HTTPX_MISSING) from exc
    return httpx


def _error_message(response: Any) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:200]
    return f"HTTP {response.status_code}: {message}"


class AsyncGoogleClient:
    """Authorized async HTTP for Google APIs, with retries and mapped errors.

    Args:
        auth: A ``GoogleAuth`` (OAuth or service account) or google-auth
            credentials.
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT).
        transport: An httpx transport (tests pass ``httpx.MockTransport``).
    """

    def __init__(self, auth: Any, *, timeout: float | None = None, transport: Any = None) -> None:
        from gsuite_core.config import get_settings

        httpx = _httpx()
        self._auth = auth
        self._client = httpx.AsyncClient(
            timeout=timeout if timeout is not None else get_settings().request_timeout,
            transport=transport,
        )
        self._refresh_lock: asyncio.Lock | None = None

    async def __aenter__(self) -> AsyncGoogleClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        await self._client.aclose()

    # ---- auth ----

    def _credentials(self) -> Any:
        credentials = getattr(self._auth, "credentials", self._auth)
        if credentials is None:
            raise NotAuthenticatedError()
        return credentials

    async def _ensure_valid(self) -> Any:
        credentials = self._credentials()
        if credentials.valid:
            return credentials
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            # Another task may have refreshed while we waited for the lock
            if not credentials.valid:
                await asyncio.to_thread(self._refresh, credentials)
        return credentials

    def _refresh(self, credentials: Any) -> None:
        """Blocking refresh (google-auth is synchronous), run in a worker thread."""
        needs_refresh = getattr(self._auth, "needs_refresh", None)
        if callable(needs_refresh) and needs_refresh():
            self._auth.refresh()  # GoogleAuth also persists the new token
            return
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request

        try:
            credentials.refresh(Request())  # e.g. service accounts: no refresh token
        except RefreshError as exc:
            raise TokenRefreshError(cause=exc) from exc

    # ---- requests ----

    async def request(
        self,
        method: str,
        url: str,
        *,
        service: str,
        resource_type: str = "resource",
        resource_id: str = "unknown",
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Send a request; returns the ``httpx.Response`` of a successful call.

        Raises:
            GSuiteError subclass for HTTP errors; the httpx network error once
            retries are exhausted.
        """
        from gsuite_core.config import get_settings

        httpx = _httpx()
        settings = get_settings()
        limiter = get_rate_limiter()
        method = method.upper()

        for attempt in range(settings.max_retries + 1):
            last_attempt = attempt == settings.max_retries
            if limiter is not None:
                await limiter.acquire_async()

            credentials = await self._ensure_valid()
            request_headers = dict(headers or {})
            credentials.apply(request_headers)

            try:
                response = await self._client.request(
                    method, url, params=params, json=json, content=content, headers=request_headers
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if last_attempt or not should_retry_status(
                    None, None, method, settings.retry_on_rate_limit
                ):
                    raise
                wait = _backoff(attempt, settings.retry_delay)
                logger.warning(
                    "%s: %s, retrying in %.1fs (attempt %d/%d)",
                    service,
                    type(exc).__name__,
                    wait,
                    attempt + 1,
                    settings.max_retries,
                )
                await asyncio.sleep(wait)
                continue

            if response.is_success:
                return response

            reason = reason_from_body(response.content)
            retry_after = parse_retry_after(response.headers.get("retry-after"))
            if not last_attempt and should_retry_status(
                response.status_code, reason, method, settings.retry_on_rate_limit
            ):
                wait = _backoff(attempt, settings.retry_delay, retry_after)
                logger.warning(
                    "%s: HTTP %d, retrying in %.1fs (attempt %d/%d)",
                    service,
                    response.status_code,
                    wait,
                    attempt + 1,
                    settings.max_retries,
                )
                await asyncio.sleep(wait)
                continue

            raise error_for_status(
                response.status_code,
                reason,
                _error_message(response),
                service,
                resource_type,
                resource_id,
                retry_after=retry_after,
            )

        raise AssertionError("unreachable")  # the loop always returns or raises

    async def json(self, method: str, url: str, **kwargs: Any) -> Any:
        """``request()`` and decode the JSON body ({} when empty)."""
        response = await self.request(method, url, **kwargs)
        return response.json() if response.content else {}

    async def paginate(
        self,
        url: str,
        items_key: str,
        *,
        service: str,
        params: dict[str, Any] | None = None,
        max_items: int | None = None,
        page_size_param: str = "maxResults",
        max_page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async ``paginate()``: yield items of a GET list endpoint, following nextPageToken."""
        yielded = 0
        page_token: str | None = None
        while max_items is None or yielded < max_items:
            remaining = max_page_size if max_items is None else max_items - yielded
            page_params = {**(params or {}), page_size_param: min(remaining, max_page_size)}
            if page_token:
                page_params["pageToken"] = page_token

            response = await self.json("GET", url, service=service, params=page_params)
            for item in response.get(items_key, []):
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            page_token = response.get("nextPageToken")
            if not page_token:
                return
