"""Property-based tests for gsuite_drive.parser (see gsuite_drive._testing.properties)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_core._testing import PropertyViolation
from gsuite_drive._testing.properties import check_parse_datetime

offsets = st.builds(
    timezone, st.timedeltas(min_value=timedelta(hours=-23), max_value=timedelta(hours=23))
)
aware_datetimes = st.datetimes(timezones=offsets | st.just(UTC))
aware_timestamps = aware_datetimes.map(datetime.isoformat) | aware_datetimes.map(
    lambda d: d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
)


def _parses_naive(value: str) -> bool:
    """B9-dates-1 input: an ISO string without an offset."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None
    except ValueError:
        return False


@given(st.none() | aware_timestamps | st.text(max_size=40).filter(lambda s: not _parses_naive(s)))
def test_parse_datetime_aware_or_none(value):
    check_parse_datetime(value)


@pytest.mark.xfail(
    strict=True,
    raises=PropertyViolation,
    reason="B9-dates-1: DriveParser._parse_datetime returns a naive datetime without offset",
)
@given(st.datetimes().map(datetime.isoformat))
@example("2024-01-01T10:00:00")
def test_parse_datetime_without_offset(value):
    check_parse_datetime(value)
