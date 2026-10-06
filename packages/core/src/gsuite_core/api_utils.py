"""Executing Google API requests: retries, error mapping, pagination, timeouts.

Every client call goes through `execute()` (one request) or `paginate()`
(a list endpoint). Retrying happens per request, so a rate limit on the
twentieth call of a listing retries that call, not the whole listing.
"""

import json
import logging
import random
import time
from collections.abc import Callable, Iterator
from functools import wraps
from typing import Any, TypeVar

import google_auth_httplib2
import httplib2
from googleapiclient.errors import HttpError

from gsuite_core.exceptions import (
    APIError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Google reports per-user/per-project throttling as 403 with these reasons
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
QUOTA_REASONS = frozenset({"quotaExceeded", "dailyLimitExceeded"})
RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})
# Safe to repeat if the first attempt may have reached the server
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})

MAX_BACKOFF = 32.0
MAX_RETRY_AFTER = 60.0


def _error_reason(error: HttpError) -> str | None:
    """The `reason` of the first error in a Google error body, if any."""
    try:
        payload = json.loads(getattr(error, "content", b"") or b"")
        reason = payload["error"]["errors"][0]["reason"]
        return str(reason)
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def _retry_after(error: HttpError) -> int | None:
    value = error.resp.get("retry-after")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None  # HTTP-date form; fall back to backoff


def _is_rate_limit(error: HttpError) -> bool:
    status = error.resp.status
    return status == 429 or (status == 403 and _error_reason(error) in RATE_LIMIT_REASONS)


def map_http_error(
    error: HttpError,
    service: str,
    resource_type: str = "resource",
    resource_id: str = "unknown",
) -> APIError:
    """
    Map Google API HttpError to domain exception.

    Args:
        error: The HttpError from Google API
        service: Service name (gmail, calendar, drive, sheets)
        resource_type: Type of resource for NotFoundError
        resource_id: ID of the resource for NotFoundError

    Returns:
        Appropriate GSuiteError subclass
    """
    status = error.resp.status
    message = str(error)
    reason = _error_reason(error)

    if status == 404:
        return NotFoundError(service, resource_type, resource_id)
    if _is_rate_limit(error):
        return RateLimitError(service, _retry_after(error))
    if status == 403:
        # Match API quota by reason; the message is only a fallback when
        # Google sent none. "storageQuotaExceeded" (the user's Drive is full)
        # is not an API quota and must not look retryable later.
        if reason in QUOTA_REASONS or (reason is None and "quota" in message.lower()):
            return QuotaExceededError(service)
        return PermissionDeniedError(service, "operation")
    return APIError(message, service, status, cause=error)


def _backoff(attempt: int, base: float, retry_after: int | None = None) -> float:
    """Seconds to wait before retry number `attempt` (0-based).

    Full jitter (random between 0 and base * 2^attempt, capped) spreads out
    clients that failed together. A server-sent Retry-After wins, capped so a
    bad header can't park a request for an hour.
    """
    if retry_after is not None:
        return float(min(retry_after, MAX_RETRY_AFTER))
    return random.uniform(0, min(MAX_BACKOFF, base * 2**attempt))


def _should_retry(error: Exception, method: str, retry_on_rate_limit: bool) -> bool:
    if isinstance(error, HttpError):
        if _is_rate_limit(error):
            return retry_on_rate_limit
        return error.resp.status in RETRYABLE_STATUSES and method in IDEMPOTENT_METHODS
    # Network failure: the request may or may not have been applied
    return method in IDEMPOTENT_METHODS


def execute(
    request: Any,
    service: str,
    resource_type: str = "resource",
    resource_id: str = "unknown",
) -> Any:
    """
    Execute a googleapiclient request with retries and mapped errors.

    Retries rate limits (429, or 403 rateLimitExceeded) on any method, and
    server errors (5xx) and network failures only on idempotent methods: a
    POST that timed out may already have sent the email.

    Raises:
        GSuiteError subclass for HTTP errors; the original network error
        once retries are exhausted.
    """
    from gsuite_core.config import get_settings

    settings = get_settings()
    method = str(getattr(request, "method", "GET")).upper()

    for attempt in range(settings.max_retries + 1):
        try:
            return request.execute()
        except (HttpError, TimeoutError, ConnectionError) as error:
            last_attempt = attempt == settings.max_retries
            if last_attempt or not _should_retry(error, method, settings.retry_on_rate_limit):
                if isinstance(error, HttpError):
                    raise map_http_error(error, service, resource_type, resource_id) from error
                raise

            retry_after = _retry_after(error) if isinstance(error, HttpError) else None
            wait = _backoff(attempt, settings.retry_delay, retry_after)
            logger.warning(
                "%s: %s, retrying in %.1fs (attempt %d/%d)",
                service,
                f"HTTP {error.resp.status}"
                if isinstance(error, HttpError)
                else type(error).__name__,
                wait,
                attempt + 1,
                settings.max_retries,
            )
            time.sleep(wait)

    raise AssertionError("unreachable")  # the loop always returns or raises


def paginate(
    list_method: Callable[..., Any],
    items_key: str,
    service: str,
    max_items: int | None = None,
    page_size_param: str = "maxResults",
    max_page_size: int = 100,
    **params: Any,
) -> Iterator[dict[str, Any]]:
    """
    Yield items from a list endpoint, following nextPageToken.

    Args:
        list_method: The bound list method, e.g. service.users().messages().list
        items_key: Key holding the items in each response ("messages", "files")
        service: Service name for error messages
        max_items: Stop after this many items (None = everything)
        page_size_param: Name of the page size parameter ("maxResults", "pageSize")
        max_page_size: Largest page the endpoint accepts
        **params: Other request parameters

    Example:
        for ref in paginate(svc.users().messages().list, "messages", "gmail",
                            max_items=1000, userId="me", q="is:unread"):
            ...
    """
    yielded = 0
    page_token: str | None = None

    while max_items is None or yielded < max_items:
        remaining = max_page_size if max_items is None else max_items - yielded
        page_params = {**params, page_size_param: min(remaining, max_page_size)}
        if page_token:
            page_params["pageToken"] = page_token

        response = execute(list_method(**page_params), service)

        for item in response.get(items_key, []):
            yield item
            yielded += 1
            if max_items is not None and yielded >= max_items:
                return

        page_token = response.get("nextPageToken")
        if not page_token:
            return


def drive_query_literal(value: str) -> str:
    """Quote a value for a Drive search query (q=...).

    Drive string literals are single-quoted with backslash escapes; an
    unescaped quote in a file name breaks the query or changes its meaning.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def authorized_http(credentials: Any, timeout: float | None = None) -> Any:
    """
    HTTP transport for googleapiclient with a request timeout.

    googleapiclient's default transport has no timeout, so a stalled
    connection hangs forever. Pass the result as `build(..., http=...)`.
    """
    from gsuite_core.config import get_settings

    timeout = timeout if timeout is not None else get_settings().request_timeout
    return google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=timeout))


def api_call(
    service: str,
    resource_type: str = "resource",
    retry_on_rate_limit: bool | None = None,
    max_retries: int | None = None,
    retry_delay: float | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for API calls with consistent error handling and retry logic.

    Retries the whole decorated function. Prefer `execute()` around each
    request inside a function that makes several calls.

    Args:
        service: Service name for error messages
        resource_type: Resource type for NotFoundError
        retry_on_rate_limit: Whether to retry on 429 errors
        max_retries: Maximum retry attempts
        retry_delay: Base delay between retries (exponential backoff)

    Example:
        @api_call("gmail", "message")
        def get_message(self, message_id: str) -> Message:
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """Apply retry logic and error mapping to the decorated function."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            """Execute the function with retry and error handling."""
            from gsuite_core.config import get_settings

            settings = get_settings()
            _retry_on_rate_limit = (
                retry_on_rate_limit
                if retry_on_rate_limit is not None
                else settings.retry_on_rate_limit
            )
            _max_retries = max_retries if max_retries is not None else settings.max_retries
            _retry_delay = retry_delay if retry_delay is not None else settings.retry_delay

            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    # The wrapped function's HTTP method is unknown; treat it
                    # as idempotent as this decorator always has.
                    retryable = _should_retry(e, "GET", _retry_on_rate_limit)
                    if attempt == _max_retries or not retryable:
                        raise map_http_error(e, service, resource_type)
                    wait = _backoff(attempt, _retry_delay, _retry_after(e))
                    logger.warning(
                        f"{service}: HTTP {e.resp.status}, retrying in {wait:.1f}s "
                        f"(attempt {attempt + 1}/{_max_retries})"
                    )
                    time.sleep(wait)

            raise AssertionError("unreachable")

        return wrapper

    return decorator


def api_call_optional(
    service: str,
    resource_type: str = "resource",
) -> Callable[[Callable[..., T | None]], Callable[..., T | None]]:
    """
    Decorator for API calls that return None on 404 instead of raising.

    Use for get-by-id operations where not-found is expected.

    Example:
        @api_call_optional("drive", "file")
        def get(self, file_id: str) -> File | None:
            ...
    """

    def decorator(func: Callable[..., T | None]) -> Callable[..., T | None]:
        """Apply optional error handling to the decorated function."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T | None:
            """Execute the function, returning None on 404 errors."""
            try:
                return func(*args, **kwargs)
            except NotFoundError:
                logger.debug(f"{service}: {resource_type} not found")
                return None
            except HttpError as e:
                if e.resp.status == 404:
                    logger.debug(f"{service}: {resource_type} not found")
                    return None
                raise map_http_error(e, service, resource_type)

        return wrapper

    return decorator
