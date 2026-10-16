"""Search Console routes (read-only)."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from gsuite_api.dependencies import SearchConsoleDep

router = APIRouter()

Dimension = Literal["query", "page", "country", "device", "date", "searchAppearance"]


class SearchFilter(BaseModel):
    dimension: Dimension
    operator: Literal[
        "equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"
    ] = "equals"
    expression: str = Field(min_length=1)


class SearchAnalyticsRequest(BaseModel):
    site_url: str = Field(min_length=1, description='e.g. "sc-domain:example.com"')
    start_date: date
    end_date: date
    dimensions: list[Dimension] = []
    filters: list[SearchFilter] = []
    row_limit: int = Field(1000, ge=1, le=25000)
    start_row: int = Field(0, ge=0)
    search_type: Literal["web", "image", "video", "news", "discover", "googleNews"] = "web"


class InspectRequest(BaseModel):
    site_url: str = Field(min_length=1)
    url: str = Field(min_length=1)
    language_code: str | None = None


@router.get("/sites")
def list_sites(sc: SearchConsoleDep) -> dict[str, Any]:
    """Properties the user can see."""
    sites = sc.list_sites()
    return {"sites": sites, "count": len(sites)}


@router.post("/searchanalytics/query")
def search_analytics(request: SearchAnalyticsRequest, sc: SearchConsoleDep) -> dict[str, Any]:
    """Search analytics rows (read-only; POST only because of the body)."""
    rows = sc.query(
        request.site_url,
        request.start_date,
        request.end_date,
        dimensions=list(request.dimensions),
        filters=[f.model_dump() for f in request.filters],
        row_limit=request.row_limit,
        start_row=request.start_row,
        search_type=request.search_type,
    )
    return {"rows": rows, "count": len(rows)}


@router.post("/urlInspection")
def inspect_url(request: InspectRequest, sc: SearchConsoleDep) -> dict[str, Any]:
    """URL Inspection result for one URL (read-only)."""
    return sc.inspect_url(request.site_url, request.url, language_code=request.language_code)


@router.get("/sitemaps")
def list_sitemaps(sc: SearchConsoleDep, site_url: str = Query(min_length=1)) -> dict[str, Any]:
    """Sitemaps submitted for a property."""
    sitemaps = sc.list_sitemaps(site_url)
    return {"sitemaps": sitemaps, "count": len(sitemaps)}
