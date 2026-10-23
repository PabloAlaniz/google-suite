"""Analytics (GA4) client on mocked discovery services."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gsuite_analytics import Analytics, ReportRow, build_filter, property_name
from gsuite_analytics.parser import parse_metric
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
        {
            "accountSummaries": [
                {
                    "name": "accountSummaries/1",
                    "account": "accounts/1",
                    "displayName": "Acme",
                    "propertySummaries": [
                        {
                            "property": "properties/9",
                            "displayName": "Web",
                            "propertyType": "PROPERTY_TYPE_ORDINARY",
                            "parent": "accounts/1",
                        }
                    ],
                }
            ],
            "nextPageToken": "p2",
        },
        {"accountSummaries": [{"account": "accounts/2"}]},
    ]
    first, second = ga.account_summaries()
    assert (first.account_id, first.display_name) == ("1", "Acme")
    assert [(p.property_id, p.display_name) for p in first.properties] == [("9", "Web")]
    assert first.properties[0].property_type == "PROPERTY_TYPE_ORDINARY"
    assert (second.account_id, second.properties) == ("2", [])


def test_list_properties_filters_by_account(ga):
    method = ga.admin.properties().list
    method.return_value.execute.return_value = {"properties": [{"name": "properties/9"}]}
    assert ga.list_properties("1")[0].property_id == "9"
    assert method.call_args.kwargs["filter"] == "parent:accounts/1"
    ga.list_properties("accounts/2")
    assert method.call_args.kwargs["filter"] == "parent:accounts/2"


def test_get_property(ga):
    ga.admin.properties().get.return_value.execute.return_value = {
        "name": "properties/9",
        "displayName": "Web",
        "timeZone": "America/Argentina/Buenos_Aires",
        "currencyCode": "ARS",
        "createTime": "2024-05-01T12:00:00.123Z",
    }
    prop = ga.get_property(9)
    assert (prop.name, prop.display_name, prop.currency_code) == ("properties/9", "Web", "ARS")
    assert prop.time_zone == "America/Argentina/Buenos_Aires"
    assert prop.create_time == datetime(2024, 5, 1, 12, 0, 0, 123000, tzinfo=UTC)
    assert prop.delete_time is None


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
    assert out.rows == [ReportRow({"country": "Argentina"}, {"activeUsers": 42})]
    assert out.row_count == 1
    assert out.raw["metricHeaders"] == [{"name": "activeUsers", "type": "TYPE_INTEGER"}]
    assert "rows" not in out.raw
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
    method.return_value.execute.return_value = {
        "metricHeaders": [{"name": "sessions"}],
        "totals": [{"metricValues": [{"value": "12.5"}]}],
    }
    out = ga.run_report("1", None, ["sessions"], order_by="date", descending=False)
    body = method.call_args.kwargs["body"]
    assert body["dateRanges"] == [{"startDate": "28daysAgo", "endDate": "today"}]
    assert body["orderBys"] == [{"dimension": {"dimensionName": "date"}, "desc": False}]
    assert out.rows == []
    assert out.row_count == 0
    assert out.totals == [ReportRow({}, {"sessions": 12.5})]


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
    assert out.rows[0].metrics["activeUsers"] == 42
    assert "dimensionFilter" in method.call_args.kwargs["body"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("42", 42), ("-3", -3), ("0.53", 0.53), ("1.2e3", 1200.0), (".5", 0.5)],
)
def test_parse_metric(value, expected):
    number = parse_metric(value)
    assert number == expected
    assert type(number) is type(expected)


@pytest.mark.parametrize("value", ["", "abc", "nan", "inf", "1e999", "1_000", " 4 ", "٤٢", None])
def test_parse_metric_rejects(value):
    assert parse_metric(value) is None
