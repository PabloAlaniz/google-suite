"""Google Analytics 4 routes (read-only)."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


@router.get("/accountSummaries")
def account_summaries(ga: AnalyticsDep) -> dict[str, Any]:
    """Accounts with their properties."""
    summaries = ga.account_summaries()
    return {"account_summaries": summaries, "count": len(summaries)}


@router.get("/properties")
def list_properties(
    ga: AnalyticsDep,
    account_id: str = Query(min_length=1, description='"123" or "accounts/123"'),
    show_deleted: bool = False,
) -> dict[str, Any]:
    """Properties of an account."""
    properties = ga.list_properties(account_id, show_deleted=show_deleted)
    return {"properties": properties, "count": len(properties)}


@router.post("/properties/{property_id}:runReport")
def run_report(property_id: str, request: ReportRequest, ga: AnalyticsDep) -> dict[str, Any]:
    """Data API runReport (read-only)."""
    return ga.run_report(
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


@router.post("/properties/{property_id}:runRealtimeReport")
def run_realtime_report(
    property_id: str, request: RealtimeRequest, ga: AnalyticsDep
) -> dict[str, Any]:
    """Data API runRealtimeReport (read-only)."""
    return ga.run_realtime_report(
        property_id,
        request.dimensions,
        request.metrics,
        dimension_filters=request.dimension_filters,
        limit=request.limit,
    )
