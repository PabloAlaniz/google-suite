"""Google Analytics 4 tools (read-only)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    ToolDecorator,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the analytics tools on the server."""

    @tool(READ)
    def analytics_account_summaries() -> dict[str, Any]:
        """GA4 accounts with their properties (use it to find property IDs)."""
        return results(to_json(svc.analytics.account_summaries()))

    @tool(READ)
    def analytics_list_properties(account_id: str, show_deleted: bool = False) -> dict[str, Any]:
        """GA4 properties of an account ("123" or "accounts/123")."""
        properties = svc.analytics.list_properties(account_id, show_deleted=show_deleted)
        return results(to_json(properties))

    @tool(READ)
    def analytics_run_report(
        property_id: str,
        metrics: list[str],
        dimensions: list[str] | None = None,
        start_date: str = "28daysAgo",
        end_date: str = "today",
        date_ranges: list[list[str]] | None = None,
        dimension_filters: list[dict[str, Any]] | None = None,
        metric_filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = True,
    ) -> dict[str, Any]:
        """GA4 Data API runReport. Metrics e.g. activeUsers, sessions,
        screenPageViews, conversions; dimensions e.g. date, country, pagePath,
        sessionSource. Dates: ISO days or today/yesterday/NdaysAgo; `date_ranges`
        ([[start, end], ...]) overrides start/end. Filters are ANDed:
        {"field": "country", "value": "Argentina"}, {"field": .., "operator":
        "CONTAINS", "value": ..}, {"field": .., "values": [..]}, numeric
        {"field": "sessions", "operator": "GREATER_THAN", "value": 10}; "not": true negates.
        Each row has `dimensions` (name -> value) and numeric `metrics`.
        """
        try:
            ranges = (
                [(start, end) for start, end in date_ranges]
                if date_ranges
                else [(start_date, end_date)]
            )
        except ValueError:
            raise ToolError("Each date range is [start, end]") from None
        report = svc.analytics.run_report(
            property_id,
            dimensions,
            metrics,
            date_ranges=ranges,
            dimension_filters=dimension_filters,
            metric_filters=metric_filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )
        return to_json(report)  # type: ignore[no-any-return]

    @tool(READ)
    def analytics_run_realtime_report(
        property_id: str,
        metrics: list[str] | None = None,
        dimensions: list[str] | None = None,
        dimension_filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GA4 realtime report (last 30 minutes). Default metric activeUsers;
        dimensions e.g. country, unifiedScreenName, deviceCategory.
        """
        report = svc.analytics.run_realtime_report(
            property_id,
            dimensions,
            metrics or ["activeUsers"],
            dimension_filters=dimension_filters,
            limit=limit,
        )
        return to_json(report)  # type: ignore[no-any-return]
