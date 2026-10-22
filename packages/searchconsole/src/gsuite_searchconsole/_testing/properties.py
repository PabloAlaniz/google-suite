"""Invariants of the ``gsuite_searchconsole`` request builders, shared by property tests
and fuzz harnesses."""

from datetime import date, datetime
from typing import Any

from gsuite_core._testing import require
from gsuite_core.exceptions import ValidationError
from gsuite_searchconsole.client import DIMENSIONS, OPERATORS, _day, build_filters


def check_build_filters(filters: list[dict[str, Any]]) -> None:
    """``build_filters`` rejects bad filters, or returns one AND group keeping each filter."""
    try:
        groups = build_filters(filters)
    except ValidationError:
        return
    if not filters:
        require(groups == [], f"no filters gave {groups!r}")
        return
    require(len(groups) == 1 and groups[0]["groupType"] == "and", f"bad groups {groups!r}")
    out = groups[0]["filters"]
    require(len(out) == len(filters), f"{len(filters)} filters -> {len(out)}")
    for f, built in zip(filters, out, strict=True):
        require(built["dimension"] in DIMENSIONS - {"date"}, f"bad dimension in {built!r}")
        require(built["operator"] in OPERATORS, f"bad operator in {built!r}")
        require(built["operator"] == f.get("operator", "equals"), f"operator changed: {built!r}")
        require(
            isinstance(built["expression"], str) and built["expression"] == f["expression"],
            f"expression changed: {f!r} -> {built!r}",
        )


def check_day(value: date | str) -> None:
    """``_day`` gives the ISO day of a date, and of any string ``date.fromisoformat`` reads."""
    try:
        day = value if isinstance(value, date) else date.fromisoformat(value)
        expected = (day.date() if isinstance(day, datetime) else day).isoformat()
    except (TypeError, ValueError):
        return
    result = _day(value)
    require(result == expected, f"_day({value!r}) = {result!r}, expected {expected!r}")
    require(_day(result) == result, f"_day is not idempotent on {result!r}")


__all__ = ["check_build_filters", "check_day"]
