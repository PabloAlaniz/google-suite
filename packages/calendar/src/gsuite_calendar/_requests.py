"""Request parameters and bodies for the Calendar API, shared by the sync and async clients."""

import logging
import uuid
from datetime import MINYEAR, UTC, date, datetime, timedelta
from typing import Any

from gsuite_calendar.parser import CalendarParser
from gsuite_core import get_settings
from gsuite_core.exceptions import ValidationError

logger = logging.getLogger("gsuite_calendar.client")

_MIN_UTC = datetime.min.replace(tzinfo=UTC)
_MAX_UTC = datetime.max.replace(tzinfo=UTC)

FreeBusy = dict[str, list[dict[str, datetime | None]]]


def rfc3339(value: datetime) -> str:
    """UTC timestamp for the API. Naive datetimes are taken as UTC.

    Appending "Z" to isoformat() (as this used to) breaks aware datetimes:
    "2026-01-01T10:00:00+00:00Z" is rejected by the API.

    Every caller passes a query bound (timeMin/timeMax). A bound whose UTC
    instant falls outside datetime's range, e.g. ``datetime.min`` in UTC+1
    used as "since forever", is clamped to the nearest representable UTC
    instant: the API holds no events out there, so the query is the same.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    try:
        value = value.astimezone(UTC)
    except OverflowError:
        value = _MIN_UTC if value.year == MINYEAR else _MAX_UTC
    return value.isoformat().replace("+00:00", "Z")


def list_params(
    time_min: datetime | None,
    time_max: datetime | None,
    single_events: bool,
    order_by: str,
) -> dict[str, Any]:
    """events.list query parameters (calendarId and paging aside)."""
    params: dict[str, Any] = {
        "timeMin": rfc3339(time_min or datetime.now(UTC)),
        "singleEvents": single_events,
    }
    # The API only accepts orderBy=startTime for expanded single events
    if order_by != "startTime" or single_events:
        params["orderBy"] = order_by
    if time_max:
        params["timeMax"] = rfc3339(time_max)
    return params


def range_params(time_min: datetime | None, time_max: datetime | None) -> dict[str, str]:
    """timeMin/timeMax for the bounds that are given."""
    params = {}
    if time_min:
        params["timeMin"] = rfc3339(time_min)
    if time_max:
        params["timeMax"] = rfc3339(time_max)
    return params


def time_bodies(
    start: datetime | date, end: datetime | date | None, all_day: bool
) -> tuple[dict[str, str], dict[str, str]]:
    """API start/end objects; end defaults to 1 hour (or the same day)."""
    if all_day or not isinstance(start, datetime):
        # datetime is a subclass of date: take .date() first, or an all-day
        # event built from a datetime sends "2026-01-01T10:00:00" as a date.
        start_date = start.date() if isinstance(start, datetime) else start
        end_date = end or start_date
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        # The API's end date is exclusive; `end` here is the last day
        return (
            {"date": start_date.isoformat()},
            {"date": (end_date + timedelta(days=1)).isoformat()},
        )

    if end is None:
        end = start + timedelta(hours=1)
    tz = get_settings().default_timezone
    # Naive datetimes are wall time in GSUITE_DEFAULT_TIMEZONE; aware ones
    # carry their own offset.
    return (
        {"dateTime": start.isoformat(), "timeZone": tz},
        {"dateTime": end.isoformat(), "timeZone": tz},
    )


def details(
    description: str | None,
    location: str | None,
    attendees: list[str] | None,
    recurrence: list[str] | None = None,
    *,
    patch: bool = False,
) -> dict[str, Any]:
    """Optional event fields. A new event omits empty ones; a patch only None ones."""
    fields: dict[str, Any] = {
        "description": description,
        "location": location,
        "attendees": None if attendees is None else [{"email": e} for e in attendees],
        "recurrence": recurrence,
    }
    if patch:
        return {key: value for key, value in fields.items() if value is not None}
    return {key: value for key, value in fields.items() if value}


def meet_request() -> dict[str, Any]:
    """conferenceData asking for a new Meet room (needs conferenceDataVersion=1)."""
    return {
        "createRequest": {
            # Idempotency key: a retried insert won't create a second room
            "requestId": uuid.uuid4().hex,
            "conferenceSolutionKey": {"type": "hangoutsMeet"},
        }
    }


def patch_body(
    summary: str | None,
    times: tuple[datetime | date | None, datetime | date | None, bool],
    fields: dict[str, Any],
) -> dict[str, Any]:
    """events.patch body; ValidationError when there's nothing to change.

    Args:
        summary: New title, or None to keep it
        times: (start, end, all_day); end alone is an error
        fields: From ``details(..., patch=True)``
    """
    start, end, all_day = times
    body: dict[str, Any] = {} if summary is None else {"summary": summary}
    body.update(fields)
    if start is not None:
        body["start"], body["end"] = time_bodies(start, end, all_day)
    elif end is not None:
        raise ValidationError("end", "pass start too when changing the time")
    if not body:
        raise ValidationError("event", "nothing to update")
    return body


def free_busy_ids(calendars: list[str]) -> list[str]:
    """The IDs to query: "me" is your primary calendar."""
    return ["primary" if c == "me" else c for c in calendars]


def free_busy_body(time_min: datetime, time_max: datetime, query_ids: list[str]) -> dict[str, Any]:
    """freebusy.query body."""
    return {
        "timeMin": rfc3339(time_min),
        "timeMax": rfc3339(time_max),
        "items": [{"id": c} for c in query_ids],
    }


def parse_free_busy(response: dict[str, Any], requested: list[str]) -> FreeBusy:
    """{calendar as requested: [{"start", "end"}, ...]}; a hidden calendar logs a warning."""
    result: FreeBusy = {}
    for name, query_id in zip(requested, free_busy_ids(requested), strict=True):
        info = response.get("calendars", {}).get(query_id, {})
        if info.get("errors"):
            logger.warning("Free/busy unavailable for %s: %s", name, info["errors"])
        result[name] = [
            {
                "start": CalendarParser._parse_datetime(b.get("start")),
                "end": CalendarParser._parse_datetime(b.get("end")),
            }
            for b in info.get("busy", [])
        ]
    return result
