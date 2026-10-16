"""Google Analytics 4 client (read-only): Admin API summaries/properties, Data API reports."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute, paginate
from gsuite_core.exceptions import ValidationError

MATCH_TYPES = {
    "EXACT",
    "BEGINS_WITH",
    "ENDS_WITH",
    "CONTAINS",
    "FULL_REGEXP",
    "PARTIAL_REGEXP",
}
NUMERIC_OPS = {
    "EQUAL",
    "LESS_THAN",
    "LESS_THAN_OR_EQUAL",
    "GREATER_THAN",
    "GREATER_THAN_OR_EQUAL",
}


def property_name(property_id: str | int) -> str:
    """ "123", 123 or "properties/123" -> "properties/123"."""
    value = str(property_id).strip()
    if value.startswith("properties/"):
        value = value.removeprefix("properties/")
    if not value.isdigit():
        raise ValidationError("property_id", f"Not a GA4 property ID: {property_id!r}")
    return f"properties/{value}"


def _filter(f: dict[str, Any]) -> dict[str, Any]:
    field = f.get("field")
    if not field:
        raise ValidationError("field", "A filter needs a field")
    if "values" in f:
        return {"fieldName": field, "inListFilter": {"values": [str(v) for v in f["values"]]}}
    op = str(f.get("operator", "EXACT")).upper()
    if op in NUMERIC_OPS:
        value = f.get("value")
        number = {"doubleValue": value} if isinstance(value, float) else {"int64Value": str(value)}
        return {"fieldName": field, "numericFilter": {"operation": op, "value": number}}
    if op not in MATCH_TYPES:
        raise ValidationError("operator", f"Unknown filter operator: {op!r}")
    return {
        "fieldName": field,
        "stringFilter": {
            "matchType": op,
            "value": str(f.get("value", "")),
            "caseSensitive": bool(f.get("case_sensitive", False)),
        },
    }


def build_filter(filters: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Simple filters ANDed together.

    Each: {"field": "country", "value": "Argentina"} (EXACT), {"field": ..,
    "operator": "CONTAINS", "value": ..}, {"field": .., "values": [..]} (in list),
    or a numeric {"operator": "GREATER_THAN", "value": 10}. "not": true negates.
    """
    if not filters:
        return None
    exprs = []
    for f in filters:
        expr: dict[str, Any] = {"filter": _filter(f)}
        if f.get("not"):
            expr = {"notExpression": expr}
        exprs.append(expr)
    return exprs[0] if len(exprs) == 1 else {"andGroup": {"expressions": exprs}}


def rows_to_dicts(data: dict[str, Any]) -> dict[str, Any]:
    """A runReport response as {"rows": [{dim: v, metric: v}], "row_count", ...}."""
    dims = [h["name"] for h in data.get("dimensionHeaders", [])]
    mets = [h["name"] for h in data.get("metricHeaders", [])]
    rows = []
    for row in data.get("rows", []):
        item = {
            n: v.get("value") for n, v in zip(dims, row.get("dimensionValues", []), strict=False)
        }
        item.update(
            {n: v.get("value") for n, v in zip(mets, row.get("metricValues", []), strict=False)}
        )
        rows.append(item)
    out: dict[str, Any] = {
        "dimensions": dims,
        "metrics": mets,
        "row_count": data.get("rowCount", len(rows)),
        "rows": rows,
    }
    if data.get("totals"):
        out["totals"] = data["totals"]
    return out


class Analytics:
    """
    Read-only Google Analytics 4 client.

    Admin API (``analyticsadmin`` v1beta) for accounts and properties, Data API
    (``analyticsdata`` v1beta) for reports. Needs ``Scopes.analytics()``.

    Example:
        ga = Analytics(auth)
        ga.account_summaries()
        ga.run_report("123456", ["date"], ["activeUsers"], [("7daysAgo", "today")])
    """

    def __init__(self, auth: GoogleAuth):
        self.auth = auth
        self._admin: Any = None
        self._data: Any = None

    @property
    def admin(self) -> Any:
        if self._admin is None:
            self._admin = build(
                "analyticsadmin",
                "v1beta",
                http=authorized_http(self.auth.credentials),
                cache_discovery=False,
            )
        return self._admin

    @property
    def data(self) -> Any:
        if self._data is None:
            self._data = build(
                "analyticsdata",
                "v1beta",
                http=authorized_http(self.auth.credentials),
                cache_discovery=False,
            )
        return self._data

    # ---------- Admin

    def account_summaries(self, max_results: int | None = None) -> list[dict[str, Any]]:
        """Accounts with their properties (the quickest way to find property IDs)."""
        return list(
            paginate(
                self.admin.accountSummaries().list,
                "accountSummaries",
                "analytics",
                max_items=max_results,
                page_size_param="pageSize",
                max_page_size=200,
            )
        )

    def list_properties(
        self, account_id: str, show_deleted: bool = False, max_results: int | None = None
    ) -> list[dict[str, Any]]:
        """Properties of an account ("123" or "accounts/123")."""
        account = account_id if account_id.startswith("accounts/") else f"accounts/{account_id}"
        return list(
            paginate(
                self.admin.properties().list,
                "properties",
                "analytics",
                max_items=max_results,
                page_size_param="pageSize",
                max_page_size=200,
                filter=f"parent:{account}",
                showDeleted=show_deleted,
            )
        )

    def get_property(self, property_id: str | int) -> dict[str, Any]:
        name = property_name(property_id)
        return dict(execute(self.admin.properties().get(name=name), "analytics", "property", name))

    # ---------- Data

    def run_report(
        self,
        property_id: str | int,
        dimensions: list[str] | None,
        metrics: list[str],
        date_ranges: list[tuple[str, str]] | None = None,
        dimension_filters: list[dict[str, Any]] | None = None,
        metric_filters: list[dict[str, Any]] | None = None,
        limit: int = 1000,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = True,
    ) -> dict[str, Any]:
        """runReport. Dates are ISO days or "today"/"yesterday"/"NdaysAgo"."""
        if not metrics:
            raise ValidationError("metrics", "At least one metric is needed")
        name = property_name(property_id)
        body: dict[str, Any] = {
            "dimensions": [{"name": d} for d in dimensions or []],
            "metrics": [{"name": m} for m in metrics],
            "dateRanges": [
                {"startDate": s, "endDate": e} for s, e in (date_ranges or [("28daysAgo", "today")])
            ],
            "limit": str(limit),
            "offset": str(offset),
        }
        dim_filter = build_filter(dimension_filters)
        if dim_filter:
            body["dimensionFilter"] = dim_filter
        met_filter = build_filter(metric_filters)
        if met_filter:
            body["metricFilter"] = met_filter
        if order_by:
            key = "metric" if order_by in metrics else "dimension"
            field = "metricName" if key == "metric" else "dimensionName"
            body["orderBys"] = [{key: {field: order_by}, "desc": descending}]
        data = execute(
            self.data.properties().runReport(property=name, body=body), "analytics", "report", name
        )
        return rows_to_dicts(data)

    def run_realtime_report(
        self,
        property_id: str | int,
        dimensions: list[str] | None,
        metrics: list[str],
        dimension_filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """runRealtimeReport (last 30 minutes)."""
        if not metrics:
            raise ValidationError("metrics", "At least one metric is needed")
        name = property_name(property_id)
        body: dict[str, Any] = {
            "dimensions": [{"name": d} for d in dimensions or []],
            "metrics": [{"name": m} for m in metrics],
            "limit": str(limit),
        }
        dim_filter = build_filter(dimension_filters)
        if dim_filter:
            body["dimensionFilter"] = dim_filter
        data = execute(
            self.data.properties().runRealtimeReport(property=name, body=body),
            "analytics",
            "realtime",
            name,
        )
        return rows_to_dicts(data)
