"""Property-based tests for gsuite_analytics (see gsuite_analytics._testing.properties)."""

from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_analytics._testing.properties import (
    check_build_filter,
    check_parse_metric,
    check_parse_report,
    check_property_name,
)
from gsuite_analytics.client import MATCH_TYPES, NUMERIC_OPS

ids = st.integers(min_value=0) | st.integers(min_value=0).map(str)
property_ids = ids | ids.map(lambda i: f"properties/{i}") | st.text(max_size=12)

numbers = (
    st.integers()
    | st.floats()
    | st.booleans()
    | st.none()
    | st.integers().map(str)
    | st.floats().map(str)
    | st.text(max_size=6)
)
operators = st.sampled_from(sorted(MATCH_TYPES | NUMERIC_OPS)) | st.text(max_size=8)
filters = st.fixed_dictionaries(
    {"field": st.text(max_size=8)},
    optional={
        "operator": operators,
        "value": numbers,
        "values": st.lists(st.integers() | st.text(max_size=5), max_size=3),
        "not": st.booleans(),
        "case_sensitive": st.booleans(),
    },
)


@given(property_ids)
@example("²")
@example("١٢٣")
@example(" 123 ")
def test_property_name(value):
    check_property_name(value)


@given(st.lists(filters, max_size=4))
@example([{"field": "x", "operator": "GREATER_THAN"}])
@example([{"field": "x", "operator": "GREATER_THAN", "value": True}])
@example([{"field": "x", "operator": "LESS_THAN", "value": "1.5"}])
@example([{"field": "x", "operator": "EQUAL", "value": float("nan")}])
def test_build_filter(value):
    check_build_filter(value)


names = st.lists(st.text(min_size=1, max_size=6), max_size=3)


@given(names, names, st.lists(st.lists(st.text(max_size=4), max_size=6), max_size=4))
def test_parse_report(dims, mets, rows):
    check_parse_report(dims, mets, rows)


metric_texts = (
    st.integers().map(str)
    | st.floats().map(str)
    | st.from_regex(r"-?[0-9]*\.?[0-9]*(e[-+]?[0-9]+)?", fullmatch=True)
    | st.text(max_size=8)
)


@given(metric_texts)
@example("1e999")
@example("nan")
@example("٤٢")
@example("1_000")
@example(" 42 ")
@example(".")
def test_parse_metric(value):
    check_parse_metric(value)
