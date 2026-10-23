"""Search Console routes (read-only)."""

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from gsuite_api.dependencies import SearchConsoleDep
from gsuite_searchconsole import SearchAnalyticsRow, Site, Sitemap, UrlInspection

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


class SiteResponse(BaseModel):
    site_url: str
    permission_level: str


class RowResponse(BaseModel):
    keys: dict[str, str]
    clicks: int
    impressions: int
    ctr: float
    position: float


class InspectionResponse(BaseModel):
    url: str
    verdict: str
    coverage_state: str | None
    indexing_state: str | None
    page_fetch_state: str | None
    robots_txt_state: str | None
    last_crawl_time: datetime | None
    crawled_as: str | None
    google_canonical: str | None
    user_canonical: str | None
    inspection_result_link: str | None
    result: dict[str, Any] = Field(
        description="The full inspectionResult (mobile usability, AMP, rich results)"
    )


class SitemapResponse(BaseModel):
    path: str
    type: str | None
    last_submitted: datetime | None
    last_downloaded: datetime | None
    is_pending: bool
    is_sitemaps_index: bool
    warnings: int
    errors: int


def _site(s: Site) -> SiteResponse:
    return SiteResponse(site_url=s.site_url, permission_level=s.permission_level)


def _row(r: SearchAnalyticsRow) -> RowResponse:
    return RowResponse(
        keys=r.keys, clicks=r.clicks, impressions=r.impressions, ctr=r.ctr, position=r.position
    )


def _sitemap(s: Sitemap) -> SitemapResponse:
    return SitemapResponse(
        path=s.path,
        type=s.type,
        last_submitted=s.last_submitted,
        last_downloaded=s.last_downloaded,
        is_pending=s.is_pending,
        is_sitemaps_index=s.is_sitemaps_index,
        warnings=s.warnings,
        errors=s.errors,
    )


def _inspection(i: UrlInspection) -> InspectionResponse:
    return InspectionResponse(
        url=i.url,
        verdict=i.verdict,
        coverage_state=i.coverage_state,
        indexing_state=i.indexing_state,
        page_fetch_state=i.page_fetch_state,
        robots_txt_state=i.robots_txt_state,
        last_crawl_time=i.last_crawl_time,
        crawled_as=i.crawled_as,
        google_canonical=i.google_canonical,
        user_canonical=i.user_canonical,
        inspection_result_link=i.inspection_result_link,
        result=i.raw,
    )


@router.get("/sites")
def list_sites(sc: SearchConsoleDep) -> dict[str, Any]:
    """Properties the user can see."""
    sites = [_site(s) for s in sc.list_sites()]
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
    return {"rows": [_row(r) for r in rows], "count": len(rows)}


@router.post("/urlInspection")
def inspect_url(request: InspectRequest, sc: SearchConsoleDep) -> InspectionResponse:
    """URL Inspection result for one URL (read-only)."""
    return _inspection(
        sc.inspect_url(request.site_url, request.url, language_code=request.language_code)
    )


@router.get("/sitemaps")
def list_sitemaps(sc: SearchConsoleDep, site_url: str = Query(min_length=1)) -> dict[str, Any]:
    """Sitemaps submitted for a property."""
    sitemaps = [_sitemap(s) for s in sc.list_sitemaps(site_url)]
    return {"sitemaps": sitemaps, "count": len(sitemaps)}
