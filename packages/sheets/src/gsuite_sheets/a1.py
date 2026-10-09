"""A1 notation: quoting sheet titles and converting ranges to GridRanges."""

import re
from typing import Any

from gsuite_core.exceptions import ValidationError

_CELL = re.compile(r"^([A-Za-z]*)(\d*)$")


def quote_title(title: str) -> str:
    """Quote a sheet title for A1 notation.

    Titles like "2024", "Q1 Budget" or "Pablo's" are ambiguous or invalid
    unquoted; quoting is always accepted, with embedded quotes doubled.
    """
    return "'" + title.replace("'", "''") + "'"


def a1(title: str, cell_range: str | None = None) -> str:
    """A1 reference to a range of a sheet, or to the whole sheet."""
    quoted = quote_title(title)
    return f"{quoted}!{cell_range}" if cell_range else quoted


def split_sheet(reference: str) -> tuple[str | None, str | None]:
    """Split an A1 reference into (sheet title, cell range).

    "'Q1 Budget'!A1:B2" -> ("Q1 Budget", "A1:B2"); "'Pablo''s'" -> ("Pablo's", None);
    "Data!A:A" -> ("Data", "A:A"); "B2" -> (None, "B2"). Quoted titles may
    contain "!" and doubled quotes, which a plain split("!") gets wrong.
    """
    if reference.startswith("'"):
        i = 1
        while i < len(reference):
            if reference[i] == "'":
                if i + 1 < len(reference) and reference[i + 1] == "'":
                    i += 2
                    continue
                break
            i += 1
        title = reference[1:i].replace("''", "'")
        rest = reference[i + 1 :]
        return title, (rest[1:] or None) if rest.startswith("!") else None
    if "!" in reference:
        title, rest = reference.split("!", 1)
        return title, rest or None
    return None, reference or None


def column_index(letters: str) -> int:
    """Zero-based index of a column letter ("A" -> 0, "AA" -> 26)."""
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def column_letter(index: int) -> str:
    """Column letter of a zero-based index (0 -> "A", 26 -> "AA")."""
    result = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _cell(ref: str, original: str) -> tuple[int | None, int | None]:
    match = _CELL.match(ref)
    if not match or not (match.group(1) or match.group(2)):
        raise ValidationError("range", f"invalid A1 range {original!r}")
    col = column_index(match.group(1)) if match.group(1) else None
    row = int(match.group(2)) - 1 if match.group(2) else None
    if row is not None and row < 0:
        raise ValidationError("range", f"rows start at 1 in {original!r}")
    return row, col


def grid_range(cell_range: str, sheet_id: int) -> dict[str, Any]:
    """
    Convert an A1 range (without sheet title) to a Sheets API GridRange.

    Supports "B2", "A1:C10", "A:C" (whole columns), "1:5" (whole rows) and
    open-ended "A2:C". Indexes are zero-based with exclusive ends. A sheet
    prefix ("'Data'!A1:B2") is ignored.
    """
    if "!" in cell_range:
        cell_range = split_sheet(cell_range)[1] or ""
    start_ref, colon, end_ref = cell_range.partition(":")
    if colon and not end_ref:
        raise ValidationError("range", f"invalid A1 range {cell_range!r}")
    start_row, start_col = _cell(start_ref, cell_range)
    end_row, end_col = _cell(end_ref, cell_range) if end_ref else (start_row, start_col)

    grid: dict[str, Any] = {"sheetId": sheet_id}
    if start_row is not None:
        grid["startRowIndex"] = start_row
    if end_row is not None:
        grid["endRowIndex"] = end_row + 1
    if start_col is not None:
        grid["startColumnIndex"] = start_col
    if end_col is not None:
        grid["endColumnIndex"] = end_col + 1
    return grid
