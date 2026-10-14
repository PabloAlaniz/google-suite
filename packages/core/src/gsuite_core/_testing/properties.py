"""Invariants of ``gsuite_core.api_utils``, shared by property tests and fuzz harnesses.

Every check takes concrete (possibly hostile) input, calls the code under test
and raises :class:`PropertyViolation` when an invariant breaks. Input outside a
function's documented domain makes the check return without asserting anything,
so fuzzers can feed arbitrary values.
"""

import math
from typing import Any

import httplib2
from googleapiclient.errors import HttpError

from gsuite_core._testing import require
from gsuite_core.api_utils import (
    MAX_BACKOFF,
    MAX_RETRY_AFTER,
    _backoff,
    drive_query_literal,
    error_for_status,
    is_rate_limited,
    map_http_error,
    parse_retry_after,
    reason_from_body,
)
from gsuite_core.exceptions import APIError, NotFoundError, RateLimitError

# _backoff computes base * 2**attempt as a float; past ~1023 the int no longer
# converts. Retries are bounded by settings.max_retries, far below this.
MAX_BACKOFF_ATTEMPT = 1000


def check_reason_from_body(body: Any) -> None:
    """``reason_from_body`` is total: ``None`` or a ``str`` for any str/bytes body."""
    if body is not None and not isinstance(body, str | bytes):
        return
    result = reason_from_body(body)
    require(result is None or isinstance(result, str), f"non-str reason {result!r}")


def check_parse_retry_after(value: Any) -> None:
    """``parse_retry_after`` never raises and yields ``None`` or seconds >= 0."""
    result = parse_retry_after(value)
    require(
        result is None or (isinstance(result, int) and result >= 0),
        f"parse_retry_after({value!r}) = {result!r}, expected None or an int >= 0",
    )


def check_backoff(attempt: int, base: float, retry_after: int | None) -> None:
    """``_backoff`` is a valid ``time.sleep`` argument, capped at the documented maxima."""
    if not 0 <= attempt <= MAX_BACKOFF_ATTEMPT or not (math.isfinite(base) and base >= 0):
        return
    wait = _backoff(attempt, base, retry_after)
    upper = MAX_BACKOFF if retry_after is None else MAX_RETRY_AFTER
    require(
        isinstance(wait, float) and 0 <= wait <= upper,
        f"_backoff({attempt}, {base}, {retry_after!r}) = {wait!r}, expected in [0, {upper}]",
    )


def check_error_for_status(
    status: int, reason: str | None, message: str, retry_after: int | None
) -> None:
    """``error_for_status`` always builds (never raises) an ``APIError`` for the status."""
    error = error_for_status(status, reason, message, "svc", retry_after=retry_after)
    require(isinstance(error, APIError), f"{type(error).__name__} is not an APIError")
    if status == 404:
        require(isinstance(error, NotFoundError), f"404 mapped to {type(error).__name__}")
    elif is_rate_limited(status, reason):
        require(
            isinstance(error, RateLimitError) and error.retry_after == retry_after,
            f"rate limit mapped to {error!r} (retry_after {retry_after!r} expected)",
        )


def check_map_http_error(status: int, body: bytes, retry_after: str | None) -> None:
    """``map_http_error`` maps any ``HttpError`` to an ``APIError`` without raising."""
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    try:
        error = HttpError(httplib2.Response(headers), body)
    except Exception:  # googleapiclient itself chokes on the body: not our code
        return
    mapped = map_http_error(error, "svc")
    require(isinstance(mapped, APIError), f"{type(mapped).__name__} is not an APIError")
    if isinstance(mapped, RateLimitError):
        expected = parse_retry_after(retry_after)
        require(mapped.retry_after == expected, "RateLimitError lost retry_after")


def _unquote_drive_literal(literal: str) -> tuple[str, int]:
    """Read a Drive string literal at the start of ``literal``: (value, end index)."""
    require(literal.startswith("'"), f"{literal!r} does not start with a quote")
    chars: list[str] = []
    i = 1
    while i < len(literal):
        char = literal[i]
        if char == "\\":
            require(i + 1 < len(literal), f"dangling backslash in {literal!r}")
            chars.append(literal[i + 1])
            i += 2
        elif char == "'":
            return "".join(chars), i
        else:
            chars.append(char)
            i += 1
    return "".join(chars), -1  # unterminated


def check_drive_query_literal(value: str) -> None:
    """The literal closes exactly at its last character and unescapes to ``value``."""
    literal = drive_query_literal(value)
    decoded, end = _unquote_drive_literal(literal)
    require(end == len(literal) - 1, f"{value!r} breaks out of its literal: {literal!r}")
    require(decoded == value, f"{literal!r} unescapes to {decoded!r}, not {value!r}")


__all__ = [
    "check_backoff",
    "check_drive_query_literal",
    "check_error_for_status",
    "check_map_http_error",
    "check_parse_retry_after",
    "check_reason_from_body",
]
