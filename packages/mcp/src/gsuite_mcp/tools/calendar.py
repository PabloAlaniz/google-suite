"""Calendar tools: list, create and delete events, free/busy."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    DESTRUCTIVE,
    READ,
    WRITE,
    ToolDecorator,
    parse_when,
    results,
)

SendUpdates = Literal["all", "externalOnly", "none"]


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the calendar tools on the server."""

    @tool(READ)
    def calendar_list_events(
        days: int = 7, calendar_id: str | None = None, max_results: int = 50
    ) -> dict[str, Any]:
        """Events from now until `days` ahead."""
        events = svc.calendar.get_upcoming(
            days=days, calendar_id=calendar_id, max_results=max_results
        )
        return results(to_json(events))

    @tool(WRITE)
    def calendar_create_event(
        summary: str,
        start: str,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        meet: bool = False,
        send_updates: SendUpdates = "none",
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an event. `start`/`end` are ISO; a date alone makes an all-day event.
        `meet` adds a Google Meet link; `send_updates="all"` emails the attendees
        (confirm with the user first).
        """
        start_at = parse_when(start)
        event = svc.calendar.create_event(
            summary=summary,
            start=start_at,
            end=parse_when(end) if end else None,
            description=description,
            location=location,
            attendees=attendees,
            all_day=not isinstance(start_at, datetime),
            meet=meet,
            send_updates=send_updates,
            calendar_id=calendar_id,
        )
        return to_json(event)  # type: ignore[no-any-return]

    @tool(DESTRUCTIVE)
    def calendar_delete_event(
        event_id: str, send_updates: SendUpdates = "none", calendar_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an event. Confirm with the user first."""
        deleted = svc.calendar.delete_event(
            event_id, calendar_id=calendar_id, send_updates=send_updates
        )
        if not deleted:
            raise ToolError(f"No event {event_id}")
        return {"deleted": event_id}

    @tool(READ)
    def calendar_free_busy(
        time_min: str, time_max: str, calendars: list[str] | None = None
    ) -> dict[str, Any]:
        """Busy intervals per calendar (default: the user's) between two ISO datetimes."""
        start, end = parse_when(time_min), parse_when(time_max)
        if not (isinstance(start, datetime) and isinstance(end, datetime)):
            raise ToolError("time_min and time_max need a time, e.g. 2026-03-02T09:00")
        return to_json(svc.calendar.get_free_busy(start, end, calendars=calendars))  # type: ignore[no-any-return]
