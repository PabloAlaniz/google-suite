"""Google Analytics 4 routes (read-only)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from gsuite_analytics import AccountSummary, Property, PropertySummary, Report, ReportRow
from gsuite_api.dependencies import AnalyticsDep

router = APIRouter()


class DateRange(BaseModel):
    start_date: str = Field("28daysAgo", description="ISO day, today, yesterday or NdaysAgo")
    end_date: str = "today"


class ReportRequest(BaseModel):
    metrics: list[str] = Field(min_length=1)
    dimensions: list[str] = []
    date_ranges: list[DateRange] = Field(
        default_factory=lambda: [DateRange(start_date="28daysAgo", end_date="today")]
    )
    dimension_filters: list[dict[str, Any]] = []
    metric_filters: list[dict[str, Any]] = []
    limit: int = Field(1000, ge=1, le=250000)
    offset: int = Field(0, ge=0)
    order_by: str | None = None
    descending: bool = True


class RealtimeRequest(BaseModel):
    metrics: list[str] = Field(default_factory=lambda: ["activeUsers"], min_length=1)
    dimensions: list[str] = []
    dimension_filters: list[dict[str, Any]] = []
    limit: int = Field(100, ge=1, le=250000)


class PropertySummaryResponse(BaseModel):
    name: str
    property_id: str
    display_name: str
    property_type: str | None
    parent: str | None


class AccountSummaryResponse(BaseModel):
    name: str
    account: str
    account_id: str
    display_name: str
    properties: list[PropertySummaryResponse]


class PropertyResponse(BaseModel):
    name: str
    property_id: str
    display_name: str
    property_type: str | None
    parent: str | None
    time_zone: str | None
    currency_code: str | None
    industry_category: str | None
    service_level: str | None
    create_time: datetime | None
    update_time: datetime | None
    delete_time: datetime | None


class ReportRowResponse(BaseModel):
    dimensions: dict[str, str]
    metrics: dict[str, int | float | None]


class ReportResponse(BaseModel):
    dimensions: list[str]
    metrics: list[str]
    rows: list[ReportRowResponse]
    row_count: int
    totals: list[ReportRowResponse]


def _property_summary(p: PropertySummary) -> PropertySummaryResponse:
    return PropertySummaryResponse(
        name=p.name,
        property_id=p.property_id,
        display_name=p.display_name,
        property_type=p.property_type,
        parent=p.parent,
    )


def _account_summary(a: AccountSummary) -> AccountSummaryResponse:
    return AccountSummaryResponse(
        name=a.name,
        account=a.account,
        account_id=a.account_id,
        display_name=a.display_name,
        properties=[_property_summary(p) for p in a.properties],
    )


def _property(p: Property) -> PropertyResponse:
    return PropertyResponse(
        name=p.name,
        property_id=p.property_id,
        display_name=p.display_name,
        property_type=p.property_type,
        parent=p.parent,
        time_zone=p.time_zone,
        currency_code=p.currency_code,
        industry_category=p.industry_category,
        service_level=p.service_level,
        create_time=p.create_time,
        update_time=p.update_time,
        delete_time=p.delete_time,
    )


def _row(r: ReportRow) -> ReportRowResponse:
    return ReportRowResponse(dimensions=r.dimensions, metrics=r.metrics)


def _report(r: Report) -> ReportResponse:
    return ReportResponse(
        dimensions=r.dimensions,
        metrics=r.metrics,
        rows=[_row(row) for row in r.rows],
        row_count=r.row_count,
        totals=[_row(row) for row in r.totals],
    )


@router.get("/accountSummaries")
def account_summaries(ga: AnalyticsDep) -> dict[str, Any]:
    """Accounts with their properties."""
    summaries = [_account_summary(a) for a in ga.account_summaries()]
    return {"account_summaries": summaries, "count": len(summaries)}


@router.get("/properties")
def list_properties(
    ga: AnalyticsDep,
    account_id: str = Query(min_length=1, description='"123" or "accounts/123"'),
    show_deleted: bool = False,
) -> dict[str, Any]:
    """Properties of an account."""
    properties = [_property(p) for p in ga.list_properties(account_id, show_deleted=show_deleted)]
    return {"properties": properties, "count": len(properties)}


@router.post("/properties/{property_id}:runReport")
def run_report(property_id: str, request: ReportRequest, ga: AnalyticsDep) -> ReportResponse:
    """Data API runReport (read-only)."""
    report = ga.run_report(
        property_id,
        request.dimensions,
        request.metrics,
        date_ranges=[(r.start_date, r.end_date) for r in request.date_ranges],
        dimension_filters=request.dimension_filters,
        metric_filters=request.metric_filters,
        limit=request.limit,
        offset=request.offset,
        order_by=request.order_by,
        descending=request.descending,
    )
    return _report(report)


@router.post("/properties/{property_id}:runRealtimeReport")
def run_realtime_report(
    property_id: str, request: RealtimeRequest, ga: AnalyticsDep
) -> ReportResponse:
    """Data API runRealtimeReport (read-only)."""
    report = ga.run_realtime_report(
        property_id,
        request.dimensions,
        request.metrics,
        dimension_filters=request.dimension_filters,
        limit=request.limit,
    )
    return _report(report)
