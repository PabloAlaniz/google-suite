"""Analytics (GA4) client on mocked discovery services."""

from unittest.mock import MagicMock

import pytest

from gsuite_analytics import Analytics, build_filter, property_name
from gsuite_core.exceptions import ValidationError

REPORT = {
    "dimensionHeaders": [{"name": "country"}],
    "metricHeaders": [{"name": "activeUsers", "type": "TYPE_INTEGER"}],
    "rows": [{"dimensionValues": [{"value": "Argentina"}], "metricValues": [{"value": "42"}]}],
    "rowCount": 1,
}


@pytest.fixture
def ga():
    client = Analytics(MagicMock(name="auth"))
    client._admin = MagicMock(name="admin")
    client._data = MagicMock(name="data")
    return client


@pytest.mark.parametrize("value", ["123", 123, "properties/123", " 123 "])
def test_property_name(value):
    assert property_name(value) == "properties/123"


@pytest.mark.parametrize("value", ["", "abc", "accounts/1", "properties/x"])
def test_property_name_rejects(value):
    with pytest.raises(ValidationError):
        property_name(value)


def test_build_filter_shapes():
    assert build_filter(None) is None
    single = build_filter([{"field": "country", "value": "Argentina"}])
    assert single == {
        "filter": {
            "fieldName": "country",
            "stringFilter": {"matchType": "EXACT", "value": "Argentina", "caseSensitive": False},
        }
    }
    group = build_filter(
        [
            {"field": "pagePath", "operator": "contains", "value": "/blog"},
            {"field": "deviceCategory", "values": ["mobile", "tablet"], "not": True},
            {"field": "sessions", "operator": "GREATER_THAN", "value": 10},
            {"field": "rate", "operator": "LESS_THAN", "value": 0.5},
        ]
    )
    exprs = group["andGroup"]["expressions"]
    assert exprs[0]["filter"]["stringFilter"]["matchType"] == "CONTAINS"
    assert exprs[1]["notExpression"]["filter"]["inListFilter"] == {"values": ["mobile", "tablet"]}
    assert exprs[2]["filter"]["numericFilter"] == {
        "operation": "GREATER_THAN",
        "value": {"int64Value": "10"},
    }
    assert exprs[3]["filter"]["numericFilter"]["value"] == {"doubleValue": 0.5}


@pytest.mark.parametrize("bad", [{"value": "x"}, {"field": "a", "operator": "LIKE", "value": "x"}])
def test_build_filter_rejects(bad):
    with pytest.raises(ValidationError):
        build_filter([bad])


def test_account_summaries_paginates(ga):
    method = ga.admin.accountSummaries().list
    method.return_value.execute.side_effect = [
        {"accountSummaries": [{"account": "accounts/1"}], "nextPageToken": "p2"},
        {"accountSummaries": [{"account": "accounts/2"}]},
    ]
    assert [s["account"] for s in ga.account_summaries()] == ["accounts/1", "accounts/2"]


def test_list_properties_filters_by_account(ga):
    method = ga.admin.properties().list
    method.return_value.execute.return_value = {"properties": [{"name": "properties/9"}]}
    assert ga.list_properties("1")[0]["name"] == "properties/9"
    assert method.call_args.kwargs["filter"] == "parent:accounts/1"
    ga.list_properties("accounts/2")
    assert method.call_args.kwargs["filter"] == "parent:accounts/2"


def test_get_property(ga):
    ga.admin.properties().get.return_value.execute.return_value = {"name": "properties/9"}
    assert ga.get_property(9) == {"name": "properties/9"}


def test_run_report(ga):
    method = ga.data.properties().runReport
    method.return_value.execute.return_value = REPORT
    out = ga.run_report(
        "123",
        ["country"],
        ["activeUsers"],
        date_ranges=[("7daysAgo", "today")],
        dimension_filters=[{"field": "country", "value": "Argentina"}],
        metric_filters=[{"field": "activeUsers", "operator": "GREATER_THAN", "value": 1}],
        limit=10,
        order_by="activeUsers",
    )
    assert out["rows"] == [{"country": "Argentina", "activeUsers": "42"}]
    assert out["row_count"] == 1
    kwargs = method.call_args.kwargs
    assert kwargs["property"] == "properties/123"
    body = kwargs["body"]
    assert body["dateRanges"] == [{"startDate": "7daysAgo", "endDate": "today"}]
    assert body["limit"] == "10"
    assert "dimensionFilter" in body
    assert "metricFilter" in body
    assert body["orderBys"] == [{"metric": {"metricName": "activeUsers"}, "desc": True}]


def test_run_report_defaults_and_dimension_order(ga):
    method = ga.data.properties().runReport
    method.return_value.execute.return_value = {"totals": [{"x": 1}]}
    out = ga.run_report("1", None, ["sessions"], order_by="date", descending=False)
    body = method.call_args.kwargs["body"]
    assert body["dateRanges"] == [{"startDate": "28daysAgo", "endDate": "today"}]
    assert body["orderBys"] == [{"dimension": {"dimensionName": "date"}, "desc": False}]
    assert out["rows"] == []
    assert out["totals"] == [{"x": 1}]


def test_reports_need_metrics(ga):
    with pytest.raises(ValidationError):
        ga.run_report("1", ["date"], [])
    with pytest.raises(ValidationError):
        ga.run_realtime_report("1", ["country"], [])


def test_run_realtime_report(ga):
    method = ga.data.properties().runRealtimeReport
    method.return_value.execute.return_value = REPORT
    out = ga.run_realtime_report(
        "123", ["country"], ["activeUsers"], dimension_filters=[{"field": "country", "value": "AR"}]
    )
    assert out["rows"][0]["activeUsers"] == "42"
    assert "dimensionFilter" in method.call_args.kwargs["body"]
