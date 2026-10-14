"""Invariants of ``gsuite_tasks.parser``, shared by property tests and fuzz harnesses."""

from datetime import date, datetime

from gsuite_core._testing import require
from gsuite_tasks.parser import format_due, parse_due, parse_timestamp


def check_parse_timestamp(value: str | None) -> None:
    """``parse_timestamp`` never raises and yields ``None`` or an aware datetime."""
    if value is not None and not isinstance(value, str):
        return
    result = parse_timestamp(value)
    require(
        result is None or (isinstance(result, datetime) and result.utcoffset() is not None),
        f"parse_timestamp({value!r}) = {result!r}, expected None or an aware datetime",
    )


def check_parse_due(value: str | None) -> None:
    """``parse_due`` never raises and yields ``None`` or a plain date."""
    if value is not None and not isinstance(value, str):
        return
    result = parse_due(value)
    require(
        result is None or (isinstance(result, date) and not isinstance(result, datetime)),
        f"parse_due({value!r}) = {result!r}, expected None or a date",
    )


def check_due_round_trip(value: date) -> None:
    """``parse_due(format_due(d))`` is the day of ``d`` (the time part is dropped)."""
    day = value.date() if isinstance(value, datetime) else value
    formatted = format_due(value)
    require(formatted.endswith("T00:00:00.000Z"), f"format_due gave {formatted!r}")
    require(parse_due(formatted) == day, f"{value!r} -> {formatted!r} does not round-trip")
    check_parse_timestamp(formatted)


__all__ = ["check_due_round_trip", "check_parse_due", "check_parse_timestamp"]
