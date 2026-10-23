"""Search Console client (read-only): sites, search analytics, URL inspection, sitemaps."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute
from gsuite_core.exceptions import ValidationError
from gsuite_searchconsole.models import SearchAnalyticsRow, Site, Sitemap, UrlInspection
from gsuite_searchconsole.parser import parse_inspection, parse_row, parse_site, parse_sitemap

DIMENSIONS = {"query", "page", "country", "device", "date", "searchAppearance"}
OPERATORS = {"equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"}
SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}
MAX_ROW_LIMIT = 25000


def _day(value: date | str) -> str:
    """ISO day; a datetime keeps only its date (the API rejects a time part)."""
    day = value if isinstance(value, date) else date.fromisoformat(value)
    return (day.date() if isinstance(day, datetime) else day).isoformat()


def build_filters(filters: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    """[{"dimension": "query", "operator": "contains", "expression": "x"}] -> filter groups."""
    if not filters:
        return []
    out = []
    for f in filters:
        dimension = f.get("dimension")
        operator = f.get("operator", "equals")
        expression = f.get("expression")
        if dimension not in DIMENSIONS - {"date"}:
            raise ValidationError("dimension", f"Unknown filter dimension: {dimension!r}")
        if operator not in OPERATORS:
            raise ValidationError("operator", f"Unknown filter operator: {operator!r}")
        if not expression:
            raise ValidationError("expression", "A filter needs an expression")
        out.append({"dimension": dimension, "operator": operator, "expression": expression})
    return [{"groupType": "and", "filters": out}]


class SearchConsole:
    """
    Read-only Google Search Console client (``searchconsole`` v1).

    Needs ``Scopes.searchconsole()`` (webmasters.readonly).

    Example:
        sc = SearchConsole(auth)
        sc.list_sites()
        sc.query("sc-domain:example.com", "2026-09-01", "2026-09-30", dimensions=["query"])
    """

    def __init__(self, auth: GoogleAuth):
        self.auth = auth
        self._service: Any = None

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = build(
                "searchconsole",
                "v1",
                http=authorized_http(self.auth.credentials),
                cache_discovery=False,
            )
        return self._service

    def list_sites(self) -> list[Site]:
        """Properties the user can see."""
        data = execute(self.service.sites().list(), "searchconsole", "sites")
        return [parse_site(s) for s in data.get("siteEntry", [])]

    def query(
        self,
        site_url: str,
        start_date: date | str,
        end_date: date | str,
        dimensions: list[str] | None = None,
        filters: list[dict[str, str]] | None = None,
        row_limit: int = 1000,
        start_row: int = 0,
        search_type: str = "web",
        aggregation_type: str | None = None,
        data_state: str | None = None,
    ) -> list[SearchAnalyticsRow]:
        """Search analytics rows: keys (dimension -> value), clicks, impressions, ctr, position."""
        dimensions = list(dimensions or [])
        unknown = set(dimensions) - DIMENSIONS
        if unknown:
            raise ValidationError("dimensions", f"Unknown dimensions: {sorted(unknown)}")
        if search_type not in SEARCH_TYPES:
            raise ValidationError("search_type", f"Unknown search type: {search_type!r}")
        if not 1 <= row_limit <= MAX_ROW_LIMIT:
            raise ValidationError("row_limit", f"row_limit must be 1..{MAX_ROW_LIMIT}")
        try:
            start, end = _day(start_date), _day(end_date)
        except ValueError as exc:
            raise ValidationError("date", f"Dates must be ISO days: {exc}") from exc
        if start > end:
            raise ValidationError("start_date", "start_date is after end_date")
        body: dict[str, Any] = {
            "startDate": start,
            "endDate": end,
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "startRow": start_row,
            "type": search_type,
        }
        groups = build_filters(filters)
        if groups:
            body["dimensionFilterGroups"] = groups
        if aggregation_type:
            body["aggregationType"] = aggregation_type
        if data_state:
            body["dataState"] = data_state
        data = execute(
            self.service.searchanalytics().query(siteUrl=site_url, body=body),
            "searchconsole",
            "searchanalytics",
            site_url,
        )
        return [parse_row(row, dimensions) for row in data.get("rows", [])]

    def query_all(
        self,
        site_url: str,
        start_date: date | str,
        end_date: date | str,
        dimensions: list[str] | None = None,
        filters: list[dict[str, str]] | None = None,
        max_rows: int | None = None,
        search_type: str = "web",
        aggregation_type: str | None = None,
        data_state: str | None = None,
    ) -> list[SearchAnalyticsRow]:
        """Every row of ``query`` (or the first ``max_rows``), paging past the 25000-row cap."""
        if max_rows is not None and max_rows < 1:
            raise ValidationError("max_rows", "max_rows must be at least 1")
        rows: list[SearchAnalyticsRow] = []
        while max_rows is None or len(rows) < max_rows:
            limit = MAX_ROW_LIMIT if max_rows is None else min(MAX_ROW_LIMIT, max_rows - len(rows))
            page = self.query(
                site_url,
                start_date,
                end_date,
                dimensions=dimensions,
                filters=filters,
                row_limit=limit,
                start_row=len(rows),
                search_type=search_type,
                aggregation_type=aggregation_type,
                data_state=data_state,
            )
            rows.extend(page)
            if len(page) < limit:
                break
        return rows

    def inspect_url(
        self, site_url: str, url: str, language_code: str | None = None
    ) -> UrlInspection:
        """URL Inspection result: index status; the full result (mobile usability, rich
        results...) is in ``raw``."""
        body: dict[str, Any] = {"inspectionUrl": url, "siteUrl": site_url}
        if language_code:
            body["languageCode"] = language_code
        data = execute(
            self.service.urlInspection().index().inspect(body=body),
            "searchconsole",
            "urlInspection",
            url,
        )
        return parse_inspection(dict(data.get("inspectionResult", {})), url)

    def list_sitemaps(self, site_url: str) -> list[Sitemap]:
        """Sitemaps submitted for a property."""
        data = execute(
            self.service.sitemaps().list(siteUrl=site_url), "searchconsole", "sitemaps", site_url
        )
        return [parse_sitemap(s) for s in data.get("sitemap", [])]
