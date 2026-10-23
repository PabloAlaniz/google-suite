"""Convert Search Console API resources to entities."""

from datetime import UTC, datetime
from typing import Any

from gsuite_searchconsole.models import SearchAnalyticsRow, Site, Sitemap, UrlInspection


def parse_timestamp(value: str | None) -> datetime | None:
    """RFC 3339 timestamp ("2026-01-01T10:00:00Z") to an aware datetime (UTC if no offset)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _int(value: Any) -> int:
    """The API sends int64 counters as strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_site(data: dict[str, Any]) -> Site:
    return Site(
        site_url=data.get("siteUrl", ""),
        permission_level=data.get("permissionLevel", ""),
        raw=data,
    )


def parse_row(data: dict[str, Any], dimensions: list[str]) -> SearchAnalyticsRow:
    return SearchAnalyticsRow(
        keys=dict(zip(dimensions, data.get("keys", []), strict=False)),
        clicks=_int(data.get("clicks", 0)),
        impressions=_int(data.get("impressions", 0)),
        ctr=float(data.get("ctr", 0.0)),
        position=float(data.get("position", 0.0)),
        raw=data,
    )


def parse_inspection(data: dict[str, Any], url: str) -> UrlInspection:
    index = data.get("indexStatusResult", {})
    return UrlInspection(
        url=url,
        verdict=index.get("verdict", "VERDICT_UNSPECIFIED"),
        coverage_state=index.get("coverageState"),
        indexing_state=index.get("indexingState"),
        page_fetch_state=index.get("pageFetchState"),
        robots_txt_state=index.get("robotsTxtState"),
        last_crawl_time=parse_timestamp(index.get("lastCrawlTime")),
        crawled_as=index.get("crawledAs"),
        google_canonical=index.get("googleCanonical"),
        user_canonical=index.get("userCanonical"),
        inspection_result_link=data.get("inspectionResultLink"),
        raw=data,
    )


def parse_sitemap(data: dict[str, Any]) -> Sitemap:
    return Sitemap(
        path=data.get("path", ""),
        type=data.get("type"),
        last_submitted=parse_timestamp(data.get("lastSubmitted")),
        last_downloaded=parse_timestamp(data.get("lastDownloaded")),
        is_pending=bool(data.get("isPending", False)),
        is_sitemaps_index=bool(data.get("isSitemapsIndex", False)),
        warnings=_int(data.get("warnings", 0)),
        errors=_int(data.get("errors", 0)),
        raw=data,
    )
