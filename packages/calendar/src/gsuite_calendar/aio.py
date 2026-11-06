"""Async Calendar: AsyncCalendar, the async counterpart of ``Calendar``.

Covers events (list, get, create, quick add, update, instances, delete),
calendars and free/busy, with the same arguments and results as the sync
client. Requests go through ``gsuite_core.aio``, so retries, rate limits and
errors are the suite's; request bodies and parsing are the sync client's own
code.

Example:
    async with AsyncCalendar(auth) as cal:
        for event in await cal.get_upcoming(days=7):
            print(event.start, event.summary)
        await cal.create_event("Standup", datetime(2026, 3, 2, 9), meet=True)

Requires ``pip install "gsuite-sdk[async]"``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from gsuite_calendar._requests import (
    FreeBusy,
    details,
    free_busy_body,
    free_busy_ids,
    list_params,
    meet_request,
    parse_free_busy,
    patch_body,
    range_params,
    time_bodies,
)
from gsuite_calendar.calendar_entity import CalendarEntity
from gsuite_calendar.client import SendUpdates
from gsuite_calendar.event import Event
from gsuite_calendar.parser import CalendarParser
from gsuite_core import get_settings
from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.exceptions import NotFoundError

API = "https://www.googleapis.com/calendar/v3"

logger = logging.getLogger("gsuite_calendar.client")


def _segment(value: str) -> str:
    """A path segment: calendar IDs carry "@" and "#" (holiday calendars)."""
    return quote(value, safe="")


class AsyncCalendar:
    """Async Calendar client.

    Args:
        auth: GoogleAuth (OAuth or service account) or google-auth credentials
        calendar_id: Default calendar ID ("primary" for the main calendar)
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT)
        transport: httpx transport (tests)
    """

    def __init__(
        self,
        auth: Any,
        calendar_id: str = "primary",
        *,
        timeout: float | None = None,
        transport: Any = None,
    ) -> None:
        self._http = AsyncGoogleClient(auth, timeout=timeout, transport=transport)
        self.calendar_id = calendar_id

    async def __aenter__(self) -> AsyncCalendar:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    def _events_url(self, calendar_id: str, *rest: str) -> str:
        return "/".join([f"{API}/calendars/{_segment(calendar_id)}/events", *map(_segment, rest)])

    async def _json(self, method: str, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("service", "calendar")
        return await self._http.json(method, url, **kwargs)

    # ---- reading ----

    async def iter_events(
        self,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int | None = 250,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> AsyncIterator[Event]:
        """Lazily yield events in a time range (default: from now), following result pages."""
        cal_id = calendar_id or self.calendar_id
        async for data in self._http.paginate(
            self._events_url(cal_id),
            "items",
            service="calendar",
            params=list_params(time_min, time_max, single_events, order_by),
            max_items=max_results,
            max_page_size=2500,
        ):
            yield CalendarParser.parse_event(data, cal_id)

    async def get_events(
        self,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int | None = 250,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> list[Event]:
        """Events in a time range (naive datetimes are UTC; None = all)."""
        return [
            event
            async for event in self.iter_events(
                time_min, time_max, calendar_id, max_results, single_events, order_by
            )
        ]

    async def get_upcoming(
        self, days: int = 7, calendar_id: str | None = None, max_results: int = 100
    ) -> list[Event]:
        """Events in the next ``days`` days."""
        now = datetime.now(UTC)
        return await self.get_events(
            now, now + timedelta(days=days), calendar_id, max_results=max_results
        )

    async def get_today(self, calendar_id: str | None = None) -> list[Event]:
        """Today's events, where "today" is in GSUITE_DEFAULT_TIMEZONE."""
        tz = ZoneInfo(get_settings().default_timezone)
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.get_events(today, today + timedelta(days=1), calendar_id)

    async def get_event(self, event_id: str, calendar_id: str | None = None) -> Event | None:
        """An event by ID, or None if it doesn't exist."""
        cal_id = calendar_id or self.calendar_id
        try:
            data = await self._json(
                "GET",
                self._events_url(cal_id, event_id),
                resource_type="event",
                resource_id=event_id,
            )
        except NotFoundError:
            return None
        return CalendarParser.parse_event(data, cal_id)

    async def get_calendars(self) -> list[CalendarEntity]:
        """All calendars you can see."""
        return [
            CalendarParser.parse_calendar(data)
            async for data in self._http.paginate(
                f"{API}/users/me/calendarList", "items", service="calendar", max_page_size=250
            )
        ]

    async def get_instances(
        self,
        event_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int | None = 250,
        calendar_id: str | None = None,
    ) -> list[Event]:
        """Occurrences of a recurring event (optionally within a time range)."""
        cal_id = calendar_id or self.calendar_id
        return [
            CalendarParser.parse_event(data, cal_id)
            async for data in self._http.paginate(
                self._events_url(cal_id, event_id, "instances"),
                "items",
                service="calendar",
                params=range_params(time_min, time_max),
                max_items=max_results,
                max_page_size=2500,
            )
        ]

    async def get_free_busy(
        self, time_min: datetime, time_max: datetime, calendars: list[str] | None = None
    ) -> FreeBusy:
        """Busy intervals per calendar ("me" = your primary; default: this client's)."""
        ids = calendars or [self.calendar_id]
        response = await self._json(
            "POST", f"{API}/freeBusy", json=free_busy_body(time_min, time_max, free_busy_ids(ids))
        )
        return parse_free_busy(response, ids)

    # ---- writing ----

    async def create_event(
        self,
        summary: str,
        start: datetime | date,
        end: datetime | date | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str | None = None,
        all_day: bool = False,
        recurrence: list[str] | None = None,
        meet: bool = False,
        send_updates: SendUpdates = "none",
    ) -> Event:
        """Create an event (same arguments as ``Calendar.create_event``)."""
        cal_id = calendar_id or self.calendar_id
        start_body, end_body = time_bodies(start, end, all_day)
        body: dict[str, Any] = {
            "summary": summary,
            "start": start_body,
            "end": end_body,
            **details(description, location, attendees, recurrence),
        }
        params: dict[str, Any] = {"sendUpdates": send_updates}
        if meet:
            body["conferenceData"] = meet_request()
            params["conferenceDataVersion"] = 1
        created = await self._json(
            "POST", self._events_url(cal_id), params=params, json=body, resource_type="event"
        )
        return CalendarParser.parse_event(created, cal_id)

    async def quick_add(
        self, text: str, calendar_id: str | None = None, send_updates: SendUpdates = "none"
    ) -> Event:
        """Create an event from natural language: "Lunch with Ana tomorrow at 1pm"."""
        cal_id = calendar_id or self.calendar_id
        created = await self._json(
            "POST",
            self._events_url(cal_id, "quickAdd"),
            params={"text": text, "sendUpdates": send_updates},
            resource_type="event",
        )
        return CalendarParser.parse_event(created, cal_id)

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        all_day: bool = False,
        calendar_id: str | None = None,
        send_updates: SendUpdates = "none",
    ) -> Event:
        """Change an event; only the arguments you pass are updated."""
        cal_id = calendar_id or self.calendar_id
        body = patch_body(
            summary, (start, end, all_day), details(description, location, attendees, patch=True)
        )
        updated = await self._json(
            "PATCH",
            self._events_url(cal_id, event_id),
            params={"sendUpdates": send_updates},
            json=body,
            resource_type="event",
            resource_id=event_id,
        )
        return CalendarParser.parse_event(updated, cal_id)

    async def delete_event(
        self, event_id: str, calendar_id: str | None = None, send_updates: SendUpdates = "none"
    ) -> bool:
        """Delete an event; False if it didn't exist (other failures raise)."""
        cal_id = calendar_id or self.calendar_id
        try:
            await self._json(
                "DELETE",
                self._events_url(cal_id, event_id),
                params={"sendUpdates": send_updates},
                resource_type="event",
                resource_id=event_id,
            )
        except NotFoundError:
            logger.warning("Event not found for deletion: %s", event_id)
            return False
        logger.info("Deleted event %s", event_id)
        return True
