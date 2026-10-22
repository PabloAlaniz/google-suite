"""Property-based tests for gsuite_searchconsole (see gsuite_searchconsole._testing.properties)."""

from datetime import date, datetime

from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_searchconsole._testing.properties import check_build_filters, check_day
from gsuite_searchconsole.client import DIMENSIONS, OPERATORS

# Mostly valid names, sometimes anything, so both branches get exercised
dimensions = st.sampled_from(sorted(DIMENSIONS)) | st.text(max_size=12)
operators = st.sampled_from(sorted(OPERATORS)) | st.text(max_size=12)
filters = st.fixed_dictionaries(
    {"dimension": dimensions, "expression": st.text(max_size=20)},
    optional={"operator": operators},
)


@given(st.lists(filters, max_size=5))
@example([{"dimension": "query", "expression": "shoes"}])
@example([{"dimension": "date", "expression": "2026-01-01"}])
def test_build_filters(value):
    check_build_filters(value)


@given(st.dates() | st.datetimes() | st.dates().map(date.isoformat) | st.text(max_size=12))
@example(datetime(2026, 1, 2, 10, 30))
@example("20260102")
def test_day(value):
    check_day(value)
