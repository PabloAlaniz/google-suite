"""Convert GA4 Admin and Data API resources to entities."""

import math
import re
from datetime import UTC, datetime
from typing import Any

from gsuite_analytics.models import AccountSummary, Property, PropertySummary, Report, ReportRow

_INT = re.compile(r"-?[0-9]+")
_FLOAT = re.compile(r"-?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")


def parse_timestamp(value: str | None) -> datetime | None:
    """RFC 3339 timestamp ("2026-01-01T10:00:00Z") to an aware datetime (UTC if no offset)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def parse_metric(value: Any) -> int | float | None:
    """A Data API metric value ("42", "0.53", "1.2e3") as a number; None if it isn't one."""
    if not isinstance(value, str):
        return None
    if _INT.fullmatch(value):
        return int(value)
    if _FLOAT.fullmatch(value):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def parse_property_summary(data: dict[str, Any]) -> PropertySummary:
    return PropertySummary(
        name=data.get("property", ""),
        display_name=data.get("displayName", ""),
        property_type=data.get("propertyType"),
        parent=data.get("parent"),
        raw=data,
    )


def parse_account_summary(data: dict[str, Any]) -> AccountSummary:
    return AccountSummary(
        name=data.get("name", ""),
        account=data.get("account", ""),
        display_name=data.get("displayName", ""),
        properties=[parse_property_summary(p) for p in data.get("propertySummaries", [])],
        raw=data,
    )


def parse_property(data: dict[str, Any]) -> Property:
    return Property(
        name=data.get("name", ""),
        display_name=data.get("displayName", ""),
        property_type=data.get("propertyType"),
        parent=data.get("parent"),
        time_zone=data.get("timeZone"),
        currency_code=data.get("currencyCode"),
        industry_category=data.get("industryCategory"),
        service_level=data.get("serviceLevel"),
        create_time=parse_timestamp(data.get("createTime")),
        update_time=parse_timestamp(data.get("updateTime")),
        delete_time=parse_timestamp(data.get("deleteTime")),
        raw=data,
    )


def _row(row: dict[str, Any], dims: list[str], mets: list[str]) -> ReportRow:
    values = zip(dims, row.get("dimensionValues", []), strict=False)
    numbers = zip(mets, row.get("metricValues", []), strict=False)
    return ReportRow(
        dimensions={n: v.get("value", "") for n, v in values},
        metrics={n: parse_metric(v.get("value")) for n, v in numbers},
    )


def parse_report(data: dict[str, Any]) -> Report:
    dims = [h["name"] for h in data.get("dimensionHeaders", [])]
    mets = [h["name"] for h in data.get("metricHeaders", [])]
    rows = [_row(r, dims, mets) for r in data.get("rows", [])]
    return Report(
        dimensions=dims,
        metrics=mets,
        rows=rows,
        row_count=int(data.get("rowCount", len(rows))),
        totals=[_row(r, dims, mets) for r in data.get("totals", [])],
        raw={k: v for k, v in data.items() if k not in ("rows", "totals")},
    )
