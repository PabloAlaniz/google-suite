"""Invariants of Calendar date handling, shared by property tests and fuzz harnesses."""

from datetime import UTC, datetime

from gsuite_calendar.client import _rfc3339
from gsuite_calendar.parser import CalendarParser
from gsuite_core._testing import require


def check_parse_datetime(value: str | None) -> None:
    """``_parse_datetime`` never raises and yields ``None`` or a datetime."""
    if value is not None and not isinstance(value, str):
        return
    result = CalendarParser._parse_datetime(value)
    require(result is None or isinstance(result, datetime), f"got {result!r} for {value!r}")


def check_parse_date(value: str | None) -> None:
    """``_parse_date`` never raises and yields ``None`` or a datetime."""
    if value is not None and not isinstance(value, str):
        return
    result = CalendarParser._parse_date(value)
    require(result is None or isinstance(result, datetime), f"got {result!r} for {value!r}")


def check_rfc3339(value: datetime) -> None:
    """``_rfc3339`` gives a "Z" timestamp for the same instant (naive taken as UTC).

    An instant outside datetime's UTC range is clamped to its nearest end.
    """
    if not isinstance(value, datetime):
        return
    text = _rfc3339(value)
    require(text.endswith("Z") and "+" not in text, f"{text!r} is not a UTC 'Z' timestamp")
    parsed = datetime.fromisoformat(text)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        expected = aware.astimezone(UTC)
    except OverflowError:
        low = aware.year == datetime.min.year
        expected = (datetime.min if low else datetime.max).replace(tzinfo=UTC)
    require(parsed == expected, f"{value!r} -> {text!r} is a different instant")


def check_event_duration(start: str | None, end: str | None, all_day: bool) -> None:
    """A parsed event's ``duration_minutes`` is computable: an int or ``None``, never raises."""
    key = "date" if all_day else "dateTime"
    if not all(v is None or isinstance(v, str) for v in (start, end)):
        return
    data = {"id": "event", "start": {key: start}, "end": {key: end}}
    event = CalendarParser.parse_event(data, "primary")
    duration = event.duration_minutes
    require(duration is None or isinstance(duration, int), f"duration {duration!r}")


__all__ = ["check_event_duration", "check_parse_date", "check_parse_datetime", "check_rfc3339"]
