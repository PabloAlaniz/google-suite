"""Invariants of ``gsuite_drive.parser``, shared by property tests and fuzz harnesses."""

from datetime import datetime

from gsuite_core._testing import require
from gsuite_drive.parser import DriveParser


def check_parse_datetime(value: str | None) -> None:
    """``_parse_datetime`` never raises and yields ``None`` or an aware datetime."""
    if value is not None and not isinstance(value, str):
        return
    result = DriveParser._parse_datetime(value)
    require(
        result is None or (isinstance(result, datetime) and result.utcoffset() is not None),
        f"_parse_datetime({value!r}) = {result!r}, expected None or an aware datetime",
    )


__all__ = ["check_parse_datetime"]
