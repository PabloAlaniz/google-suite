"""API utilities for consistent error handling and retries."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

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


def map_http_error(error: HttpError, service: str, resource_type: str = "resource") -> APIError:
    """
    Map Google API HttpError to domain exception.

    Args:
        error: The HttpError from Google API
        service: Service name (gmail, calendar, drive, sheets)
        resource_type: Type of resource for NotFoundError

    Returns:
        Appropriate GSuiteError subclass
    """
    status = error.resp.status
    message = str(error)

    if status == 404:
        # Extract resource ID from error if possible
        resource_id = "unknown"
        return NotFoundError(service, resource_type, resource_id)
    elif status == 403:
        if "quota" in message.lower():
            return QuotaExceededError(service)
        return PermissionDeniedError(service, "operation")
    elif status == 429:
        # Try to extract retry-after header
        retry_after = error.resp.get("retry-after")
        return RateLimitError(service, int(retry_after) if retry_after else None)
    else:
        return APIError(message, service, status, cause=error)


def api_call(
    service: str,
    resource_type: str = "resource",
    retry_on_rate_limit: bool | None = None,
    max_retries: int | None = None,
    retry_delay: float | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for API calls with consistent error handling and retry logic.

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
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Import here to avoid circular imports
            from gsuite_core.config import get_settings

            settings = get_settings()

            # Use provided values or fall back to settings
            _retry_on_rate_limit = (
                retry_on_rate_limit
                if retry_on_rate_limit is not None
                else settings.retry_on_rate_limit
            )
            _max_retries = max_retries if max_retries is not None else settings.max_retries
            _retry_delay = retry_delay if retry_delay is not None else settings.retry_delay

            last_error = None

            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    last_error = e
                    status = e.resp.status

                    # Retry on rate limit
                    if status == 429 and _retry_on_rate_limit and attempt < _max_retries:
                        wait_time = _retry_delay * (2**attempt)
                        logger.warning(
                            f"{service}: Rate limited, retrying in {wait_time:.1f}s "
                            f"(attempt {attempt + 1}/{_max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    # Retry on server errors (5xx)
                    if 500 <= status < 600 and attempt < _max_retries:
                        wait_time = _retry_delay * (2**attempt)
                        logger.warning(
                            f"{service}: Server error {status}, retrying in {wait_time:.1f}s "
                            f"(attempt {attempt + 1}/{_max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    # Don't retry other errors
                    raise map_http_error(e, service, resource_type)

            # Exhausted retries
            if last_error:
                raise map_http_error(last_error, service, resource_type)

            # Should never reach here
            raise RuntimeError("Unexpected state in api_call")

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
        @wraps(func)
        def wrapper(*args, **kwargs) -> T | None:
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                if e.resp.status == 404:
                    logger.debug(f"{service}: {resource_type} not found")
                    return None
                raise map_http_error(e, service, resource_type)

        return wrapper

    return decorator
