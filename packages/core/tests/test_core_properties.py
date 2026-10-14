"""Property-based tests for gsuite_core.api_utils (see gsuite_core._testing.properties)."""

import json
import math
from unittest.mock import Mock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError
from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_core._testing.properties import (
    check_backoff,
    check_drive_query_literal,
    check_error_for_status,
    check_map_http_error,
    check_parse_retry_after,
    check_reason_from_body,
)
from gsuite_core.api_utils import execute, reason_from_body

REASONS = ["rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded"]

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.sampled_from(["error", "errors", "reason", "message", "x"]), children)
    ),
    max_leaves=12,
)


@st.composite
def google_error_bodies(draw: st.DrawFn) -> str:
    """Bodies shaped like Google errors, with arbitrary values in every slot."""
    reason = draw(st.sampled_from(REASONS) | json_values)
    message = draw(st.text(max_size=30))
    error = {"code": draw(st.integers()), "message": message, "errors": [{"reason": reason}]}
    return json.dumps({"error": error})


bodies = (
    st.none()
    | st.text(max_size=200)
    | st.binary(max_size=200)
    | json_values.map(json.dumps)
    | google_error_bodies()
    | google_error_bodies().map(str.encode)
)


def _negative_int(value: object) -> bool:
    """B4a input: a header ``int()`` reads as a negative number."""
    try:
        return int(value) < 0  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return False


http_dates = st.datetimes().map(lambda d: d.strftime("%a, %d %b %Y %H:%M:%S GMT"))
retry_after_headers = (
    st.none()
    | st.integers(min_value=0)
    | st.integers(min_value=0).map(str)
    | http_dates
    | st.floats(min_value=0, allow_infinity=False)
    | st.just(math.nan)
    | st.text(max_size=20).filter(lambda s: not _negative_int(s))
    | st.binary(max_size=20).filter(lambda s: not _negative_int(s))
)


# ---- reason_from_body ----


@given(bodies)
def test_reason_from_body_is_total(body):
    check_reason_from_body(body)


@given(st.sampled_from(REASONS) | st.text(max_size=30))
def test_reason_from_body_extracts_reason(reason):
    body = json.dumps({"error": {"errors": [{"reason": reason}]}})
    assert reason_from_body(body) == reason
    assert reason_from_body(body.encode()) == reason


@pytest.mark.xfail(
    strict=True,
    raises=RecursionError,
    reason="B4c: deeply nested JSON body raises RecursionError",
)
@given(st.integers(min_value=50_000, max_value=200_000))
@example(100_000)
def test_reason_from_body_deep_nesting(depth):
    check_reason_from_body("[" * depth)


# ---- parse_retry_after ----


@given(retry_after_headers)
def test_parse_retry_after_non_negative_or_none(value):
    check_parse_retry_after(value)


@given(st.integers(max_value=-1).map(str))
@example("-5")
def test_parse_retry_after_negative(value):
    check_parse_retry_after(value)


@given(st.sampled_from([math.inf, -math.inf]))
@example(math.inf)
def test_parse_retry_after_infinite(value):
    check_parse_retry_after(value)


# ---- _backoff ----


@given(
    st.integers(min_value=0, max_value=1000),
    st.floats(min_value=0, max_value=1e6),
    st.none() | st.integers(min_value=0),
)
def test_backoff_within_bounds(attempt, base, retry_after):
    check_backoff(attempt, base, retry_after)


@given(st.integers(max_value=-1))
@example(-5)
def test_backoff_negative_retry_after(retry_after):
    check_backoff(0, 1.0, retry_after)


def _strict_sleep(seconds: float) -> None:
    """time.sleep's argument contract, without sleeping."""
    if seconds < 0:
        raise ValueError("sleep length must be non-negative")


@given(st.integers(min_value=-3600, max_value=-1))
@example(-5)
def test_execute_survives_negative_retry_after(retry_after):
    throttled = HttpError(
        httplib2.Response({"status": "429", "retry-after": str(retry_after)}), b"{}"
    )
    request = Mock(method="GET")
    request.execute.side_effect = [throttled, {"ok": True}]
    with patch("gsuite_core.api_utils.time.sleep", side_effect=_strict_sleep):
        assert execute(request, "svc") == {"ok": True}


# ---- error mapping ----


@given(
    st.integers(),
    st.none() | st.sampled_from(REASONS) | st.text(max_size=30),
    st.text(max_size=100),
    st.none() | st.integers(),
)
def test_error_for_status_always_api_error(status, reason, message, retry_after):
    check_error_for_status(status, reason, message, retry_after)


@given(
    st.integers(min_value=-1000, max_value=1000) | st.sampled_from([403, 404, 429, 500, 503]),
    bodies.map(lambda b: b.encode() if isinstance(b, str) else (b or b"")),
    st.none() | st.text(max_size=20),
)
def test_map_http_error_always_api_error(status, body, retry_after):
    check_map_http_error(status, body, retry_after)


# ---- drive_query_literal ----


@given(st.text())
@example("it's")
@example("a\\'b")
@example("\\")
def test_drive_query_literal_round_trips(value):
    check_drive_query_literal(value)
