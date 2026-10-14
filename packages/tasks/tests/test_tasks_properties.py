"""Property-based tests for gsuite_tasks.parser (see gsuite_tasks._testing.properties)."""

from datetime import UTC, datetime, timedelta, timezone

from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_tasks._testing.properties import (
    check_due_round_trip,
    check_parse_due,
    check_parse_timestamp,
)

offsets = st.builds(
    timezone, st.timedeltas(min_value=timedelta(hours=-23), max_value=timedelta(hours=23))
)
aware_datetimes = st.datetimes(timezones=offsets | st.just(UTC))
aware_timestamps = aware_datetimes.map(datetime.isoformat) | aware_datetimes.map(
    lambda d: d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
)
naive_timestamps = st.datetimes().map(datetime.isoformat)


def _parses_naive(value: str) -> bool:
    """B7a input: an ISO string without an offset."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None
    except ValueError:
        return False


@given(st.none() | aware_timestamps | st.text(max_size=40).filter(lambda s: not _parses_naive(s)))
def test_parse_timestamp_aware_or_none(value):
    check_parse_timestamp(value)


@given(naive_timestamps)
@example("2024-01-01T10:00:00")
def test_parse_timestamp_without_offset(value):
    check_parse_timestamp(value)


@given(st.none() | aware_timestamps | naive_timestamps | st.text(max_size=40))
def test_parse_due_total(value):
    check_parse_due(value)


@given(st.dates() | st.datetimes() | aware_datetimes)
def test_due_round_trip(value):
    check_due_round_trip(value)
