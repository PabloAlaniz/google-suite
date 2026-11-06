"""Search Console tools (read-only)."""

from __future__ import annotations

from typing import Any, Literal

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    ToolDecorator,
    results,
)

SCDimension = Literal["query", "page", "country", "device", "date", "searchAppearance"]


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the searchconsole tools on the server."""

    @tool(READ)
    def searchconsole_list_sites() -> dict[str, Any]:
        """Search Console properties the user can see (siteUrl, permissionLevel).
        Domain properties look like "sc-domain:example.com".
        """
        return results(to_json(svc.searchconsole.list_sites()))

    @tool(READ)
    def searchconsole_query(
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[SCDimension] | None = None,
        filters: list[dict[str, str]] | None = None,
        row_limit: int = 100,
        start_row: int = 0,
        search_type: Literal["web", "image", "video", "news", "discover", "googleNews"] = "web",
    ) -> dict[str, Any]:
        """Search analytics: clicks, impressions, ctr and position, grouped by
        `dimensions` (each row's `keys` maps dimension -> value). Dates are ISO
        days (data lags ~2-3 days). `filters` are ANDed:
        [{"dimension": "query", "operator": "contains", "expression": "shoes"}];
        operators: equals, notEquals, contains, notContains, includingRegex, excludingRegex.
        `row_limit` max 25000.
        """
        rows = svc.searchconsole.query(
            site_url,
            start_date,
            end_date,
            dimensions=list(dimensions or []),
            filters=filters,
            row_limit=row_limit,
            start_row=start_row,
            search_type=search_type,
        )
        return results(to_json(rows))

    @tool(READ)
    def searchconsole_inspect_url(
        site_url: str, url: str, language_code: str | None = None
    ) -> dict[str, Any]:
        """URL Inspection: Google index status, coverage, canonical and last
        crawl for one URL of a property; `raw` has the full result (mobile
        usability, rich results).
        """
        inspection = svc.searchconsole.inspect_url(site_url, url, language_code=language_code)
        return to_json(inspection, skip=set())  # type: ignore[no-any-return]

    @tool(READ)
    def searchconsole_list_sitemaps(site_url: str) -> dict[str, Any]:
        """Sitemaps submitted for a property, with status, errors and warnings."""
        return results(to_json(svc.searchconsole.list_sitemaps(site_url)))
