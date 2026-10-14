"""Property-based tests for Calendar dates (see gsuite_calendar._testing.properties)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_calendar._testing.properties import (
    check_event_duration,
    check_parse_date,
    check_parse_datetime,
    check_rfc3339,
)

offsets = st.builds(
    timezone, st.timedeltas(min_value=timedelta(hours=-23), max_value=timedelta(hours=23))
)
# One day inside datetime's range, so converting to UTC cannot leave it (see B9-dates-2)
in_range = {"min_value": datetime(1, 1, 2), "max_value": datetime(9999, 12, 30)}
aware_datetimes = st.datetimes(**in_range, timezones=offsets | st.just(UTC))
aware_timestamps = aware_datetimes.map(datetime.isoformat) | aware_datetimes.map(
    lambda d: d.astimezone(UTC).isoformat().replace("+00:00", "Z")
)
naive_timestamps = st.datetimes().map(datetime.isoformat)
dates = st.dates().map(lambda d: d.isoformat())


@given(st.none() | aware_timestamps | naive_timestamps | st.text(max_size=40))
def test_parse_datetime_total(value):
    check_parse_datetime(value)


@given(st.none() | dates | naive_timestamps | st.text(max_size=40))
def test_parse_date_total(value):
    check_parse_date(value)


@given(st.datetimes(**in_range) | aware_datetimes)
def test_rfc3339_is_utc_same_instant(value):
    check_rfc3339(value)


@pytest.mark.xfail(
    strict=True,
    raises=OverflowError,
    reason="B9-dates-2: _rfc3339 overflows for datetimes whose UTC instant is out of range",
)
@given(
    st.sampled_from(
        [
            datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
            datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),
        ]
    )
)
@example(datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))))
def test_rfc3339_at_datetime_range_edges(value):
    check_rfc3339(value)


@given(
    st.one_of(
        st.tuples(st.none() | aware_timestamps, st.none() | aware_timestamps, st.just(False)),
        st.tuples(st.none() | naive_timestamps, st.none() | naive_timestamps, st.just(False)),
        st.tuples(st.none() | dates, st.none() | dates, st.just(True)),
    )
)
def test_event_duration_computable(case):
    check_event_duration(*case)


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="B7c: duration_minutes raises when only one of start/end has an offset",
)
@given(naive_timestamps, aware_timestamps)
@example("2024-01-01T10:00:00", "2024-01-01T11:00:00Z")
def test_event_duration_mixed_offsets(start, end):
    check_event_duration(start, end, all_day=False)
