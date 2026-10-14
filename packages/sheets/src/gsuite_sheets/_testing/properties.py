"""Invariants of the Sheets package, shared by property tests and fuzz harnesses.

Every check takes concrete (possibly hostile) input, calls the code under test
and raises :class:`PropertyViolation` when an invariant breaks. Exceptions the
code is documented to raise for invalid input are accepted outcomes; anything
else propagates, so fuzzers can feed arbitrary values.
"""

from __future__ import annotations

import dataclasses
import math
import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from gsuite_core._testing import PropertyViolation, require
from gsuite_core.exceptions import ValidationError
from gsuite_sheets.a1 import a1, column_index, column_letter, grid_range, quote_title, split_sheet
from gsuite_sheets.engine.domain.batching import split_range_data, split_rows
from gsuite_sheets.engine.domain.errors import (
    InvalidColorError,
    InvalidIdentifierError,
    InvalidRangeError,
    SchemaError,
)
from gsuite_sheets.engine.domain.numericise import numericise
from gsuite_sheets.engine.domain.schema import _coerce, models_to_rows, rows_to_models
from gsuite_sheets.engine.domain.values.color import Color
from gsuite_sheets.engine.domain.values.ranges import A1Range, GridRange, SpreadsheetId

# Google Sheets allows at most 18278 columns (A..ZZZ).
MAX_COLUMNS = 18278

_HEX_COLOR = re.compile(r"#?[0-9A-Fa-f]{6}")
_CANONICAL_INT = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
_LEADING_ZERO_DIGITS = re.compile(r"[+-]?0[0-9]+")
_ASCII_FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_SPREADSHEET_KEY = re.compile(r"[A-Za-z0-9_-]+")


# --- A1 notation -----------------------------------------------------------


def check_column_round_trip(index: int) -> None:
    """``column_index(column_letter(i)) == i`` for every column Sheets can address."""
    if not 0 <= index < MAX_COLUMNS:
        return
    letters = column_letter(index)
    require(letters.isascii() and letters.isupper(), f"column_letter({index}) = {letters!r}")
    require(1 <= len(letters) <= 3, f"column_letter({index}) = {letters!r} exceeds ZZZ")
    require(column_index(letters) == index, f"{index} -> {letters!r} -> {column_index(letters)}")
    require(column_index(letters.lower()) == index, f"lowercase {letters!r} differs")


def check_a1_split_round_trip(title: str, cell_range: str | None) -> None:
    """``split_sheet(a1(title, r)) == (title, r)`` for any title and non-empty range."""
    reference = a1(title, cell_range)
    expected = (title, cell_range or None)
    result = split_sheet(reference)
    require(result == expected, f"split_sheet({reference!r}) = {result!r}, want {expected!r}")
    require(quote_title(title).startswith("'"), f"quote_title({title!r}) is not quoted")


def check_split_sheet_lossless(reference: str) -> None:
    """``split_sheet`` never silently drops characters: its parts rebuild ``reference``.

    Malformed references may raise ``ValidationError``; returning a title and range
    that do not reconstruct the input means part of it was silently discarded.
    """
    try:
        title, cell_range = split_sheet(reference)
    except ValidationError:
        return
    if reference.startswith("'"):
        require(title is not None, f"quoted {reference!r} lost its title")
        quoted = quote_title(title or "")
        rebuilt = {quoted + "!" + cell_range} if cell_range else {quoted, quoted + "!"}
        require(
            reference in rebuilt,
            f"split_sheet({reference!r}) = {(title, cell_range)!r} drops part of the input",
        )
    elif "!" in reference:
        require(
            title is not None and f"{title}!{cell_range or ''}" == reference,
            f"split_sheet({reference!r}) = {(title, cell_range)!r}",
        )
    else:
        require(
            (title, cell_range) == (None, reference or None),
            f"split_sheet({reference!r}) = {(title, cell_range)!r}",
        )


def check_grid_range_total(cell_range: str, sheet_id: int = 0) -> None:
    """``grid_range`` only ever raises ``ValidationError``, and returns a dict otherwise."""
    try:
        grid = grid_range(cell_range, sheet_id)
    except ValidationError:
        return
    require(isinstance(grid, dict), f"grid_range({cell_range!r}) = {grid!r}")
    require(grid.get("sheetId") == sheet_id, f"sheetId lost in {grid!r}")


def _range_part(cell_range: str) -> str:
    if "!" in cell_range:
        return split_sheet(cell_range)[1] or ""
    return cell_range


def check_grid_range(cell_range: str, sheet_id: int = 0) -> None:
    """An accepted range yields a non-empty, in-bounds, zero-based GridRange.

    Indexes are ints >= 0, ``start < end`` on each bounded axis, columns stay within
    ``ZZZ`` and the cell reference itself is ASCII (Sheets only knows ASCII A1).
    """
    try:
        grid = grid_range(cell_range, sheet_id)
    except ValidationError:
        return
    require(grid.get("sheetId") == sheet_id, f"sheetId lost in {grid!r}")
    for key, value in grid.items():
        if key != "sheetId":
            require(type(value) is int and value >= 0, f"{key}={value!r} in {cell_range!r}")
    require(_range_part(cell_range).isascii(), f"non-ASCII range accepted: {cell_range!r}")
    for axis in ("Row", "Column"):
        start, end = grid.get(f"start{axis}Index"), grid.get(f"end{axis}Index")
        if start is not None and end is not None:
            require(start < end, f"{cell_range!r} -> empty/reversed {axis.lower()}s {grid!r}")
    for key in ("startColumnIndex", "endColumnIndex"):
        limit = MAX_COLUMNS - 1 if key == "startColumnIndex" else MAX_COLUMNS
        value = grid.get(key, 0)
        require(value <= limit, f"{cell_range!r} -> {key}={value} beyond ZZZ")


def check_a1range_agrees_with_grid_range(cell_range: str, sheet_id: int = 0) -> None:
    """Whatever ``A1Range`` validates, ``grid_range``/``GridRange.from_a1`` also accept."""
    try:
        A1Range(cell_range)
    except InvalidRangeError:
        return
    try:
        grid = grid_range(cell_range, sheet_id)
    except ValidationError as exc:
        raise PropertyViolation(f"A1Range accepts {cell_range!r}, grid_range: {exc}") from exc
    from_a1 = GridRange.from_a1(cell_range, sheet_id).to_dict()
    require(from_a1 == grid, f"{cell_range!r}: from_a1 {from_a1!r} != grid_range {grid!r}")


# --- Colors ------------------------------------------------------------------


def check_color_from_hex(hex_color: str) -> None:
    """``Color.from_hex`` accepts exactly ``#?[0-9A-Fa-f]{6}``; anything else raises
    ``InvalidColorError`` (any other exception propagates)."""
    valid = _HEX_COLOR.fullmatch(hex_color) is not None
    try:
        color = Color.from_hex(hex_color)
    except InvalidColorError:
        require(not valid, f"valid hex {hex_color!r} rejected")
        return
    require(valid, f"invalid hex {hex_color!r} accepted as {color!r}")
    digits = hex_color.removeprefix("#")
    expected = tuple(int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
    require((color.red, color.green, color.blue) == expected, f"{hex_color!r} -> {color!r}")
    require(all(0.0 <= c <= 1.0 for c in expected) and color.alpha == 1.0, f"{color!r}")


# --- numericise ------------------------------------------------------------


def check_numericise(value: str) -> None:
    """Contract of ``numericise`` for a cell string.

    - ``""`` -> ``default_blank`` (``""``).
    - Canonical ASCII integers (optional sign, no leading zeros, surrounding
      whitespace tolerated) -> ``int``; ASCII decimal/scientific notation -> finite
      ``float``.
    - Everything else stays the same string: digits with leading zeros (signed or
      not), underscores, non-ASCII digits, ``nan``/``inf``.
    """
    result = numericise(value)
    if value == "":
        require(result == "", f"numericise('') = {result!r}")
        return
    text = value.strip()
    if type(result) is int:
        require(
            _CANONICAL_INT.fullmatch(text) is not None,
            f"numericise({value!r}) = {result!r}: not a canonical ASCII integer",
        )
        require(result == int(text), f"numericise({value!r}) = {result!r}")
    elif type(result) is float:
        require(math.isfinite(result), f"numericise({value!r}) = {result!r} (non-finite)")
        require(
            _ASCII_FLOAT.fullmatch(text) is not None,
            f"numericise({value!r}) = {result!r}: not an ASCII number",
        )
        require(result == float(text), f"numericise({value!r}) = {result!r}")
    else:
        require(result is value, f"numericise({value!r}) = {result!r} (changed string)")
        if text != value:
            return  # padding is tolerated, not required to convert (str.strip != int())
        require(
            _CANONICAL_INT.fullmatch(text) is None,
            f"integer {value!r} left as a string",
        )
        if _ASCII_FLOAT.fullmatch(text) and not _LEADING_ZERO_DIGITS.fullmatch(text):
            require(not math.isfinite(float(text)), f"number {value!r} left as a string")


# --- schema ------------------------------------------------------------------


@dataclasses.dataclass
class SchemaRecord:
    """Model exercising every scalar type ``rows_to_models`` coerces."""

    text: str
    count: int
    ratio: float
    flag: bool
    day: date
    note: str | None = None
    score: int | None = None


RecordFields = tuple[str, int, float, bool, date, str | None, int | None]


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float) and math.isnan(left):
        return math.isnan(right)
    return bool(type(left) is type(right) and left == right)


def check_schema_round_trip(records: list[RecordFields]) -> None:
    """Models written as cells and read back as strings come back equal.

    An ``Optional[str]`` field holding ``""`` reads back as ``None`` (documented: an
    empty cell means "no value"), so that is the expected value in that case.
    """
    models = [SchemaRecord(*fields) for fields in records]
    header, rows = models_to_rows(models)
    cells = [[cell if isinstance(cell, str) else str(cell) for cell in row] for row in rows]
    back = rows_to_models(SchemaRecord, header, cells) if models else []
    require(len(back) == len(models), f"{len(models)} models -> {len(back)}")
    for model, parsed in zip(models, back, strict=True):
        for field in dataclasses.fields(SchemaRecord):
            want = getattr(model, field.name)
            if field.name == "note" and want == "":
                want = None
            got = getattr(parsed, field.name)
            require(_same_value(want, got), f"{field.name}: {want!r} -> {got!r}")


class _Level(Enum):
    LOW = "low"
    HIGH = 2


COERCE_TYPES: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "Decimal": Decimal,
    "date": date,
    "datetime": datetime,
    "Enum": _Level,
    "Literal": Literal["a", 1],
    "int | None": int | None,
    "date | None": date | None,
}


def check_coerce(value: str, kind: str) -> None:
    """``_coerce`` returns the annotated type or raises ``SchemaError``, nothing else."""
    annotation = COERCE_TYPES.get(kind)
    if annotation is None:
        return
    try:
        result = _coerce(value, annotation, "field")
    except SchemaError:
        return
    if kind.endswith("| None") and value == "":
        require(result is None, f"_coerce('', {kind}) = {result!r}")
        return
    expected: Any = {"Enum": _Level, "Literal": (str, int)}.get(kind)
    if expected is None:
        expected = COERCE_TYPES[kind.removesuffix(" | None")]
    require(isinstance(result, expected), f"_coerce({value!r}, {kind}) = {result!r}")
    if kind == "date":
        require(type(result) is date, f"_coerce({value!r}, date) = {result!r}")


# --- batching ----------------------------------------------------------------


def _check_chunks(items: list[Any], chunks: list[list[Any]], sizes: list[int], cap: int) -> None:
    flat = [item for chunk in chunks for item in chunk]
    require(flat == items, f"chunks do not concatenate back to the input: {chunks!r}")
    require(all(chunks) or not items, f"empty chunk in {chunks!r}")
    position = 0
    for chunk in chunks:
        cells = sum(sizes[position : position + len(chunk)])
        position += len(chunk)
        require(cells <= cap or len(chunk) == 1, f"chunk of {cells} cells > {cap}: {chunk!r}")


def check_split_rows(rows: list[list[Any]], max_cells: int | None) -> None:
    """Chunks concatenate to ``rows`` in order; each fits ``max_cells`` unless it is one row."""
    chunks = split_rows(rows, max_cells)
    if max_cells is None:
        require(chunks == [rows], "max_cells=None must not split")
        return
    _check_chunks(rows, chunks, [len(row) for row in rows], max_cells)


def check_split_range_data(range_data: list[dict[str, Any]], max_cells: int | None) -> None:
    """Same as :func:`check_split_rows` for ``values:batchUpdate`` range items."""
    chunks = split_range_data(range_data, max_cells)
    if max_cells is None:
        require(chunks == [range_data], "max_cells=None must not split")
        return
    sizes = [sum(len(row) for row in item.get("values", [])) for item in range_data]
    _check_chunks(range_data, chunks, sizes, max_cells)


# --- GridRange / SpreadsheetId ----------------------------------------------

Bounds = tuple[int | None, int | None, int | None, int | None]


def _cells(bounds: Bounds, limit: int) -> set[tuple[int, int]]:
    start_row, end_row, start_col, end_col = bounds
    rows = range(start_row or 0, limit if end_row is None else end_row)
    cols = range(start_col or 0, limit if end_col is None else end_col)
    return {(r, c) for r in rows for c in cols}


def check_grid_range_overlaps(first: Bounds, second: Bounds) -> None:
    """``overlaps`` is symmetric and equals "the cell sets intersect".

    Bounds are ``(start_row, end_row, start_col, end_col)``; ``None`` is unbounded.
    Negative or reversed (start > end) bounds are outside the domain.
    """
    for bounds in (first, second):
        if any(b is not None and b < 0 for b in bounds):
            return
        for start, end in ((bounds[0], bounds[1]), (bounds[2], bounds[3])):
            if start is not None and end is not None and start > end:
                return
    a, b = GridRange(0, *first), GridRange(0, *second)
    require(a.overlaps(b) == b.overlaps(a), f"overlaps not symmetric: {first} vs {second}")
    limit = max([v for v in (*first, *second) if v is not None], default=0) + 1
    brute = bool(_cells(first, limit) & _cells(second, limit))
    require(
        a.overlaps(b) == brute, f"overlaps({first}, {second}) = {a.overlaps(b)}, cells say {brute}"
    )


def check_spreadsheet_id_from_url(url: str) -> None:
    """``from_url`` returns a key that appears after ``/spreadsheets/d/`` or raises
    ``InvalidIdentifierError``."""
    try:
        sid = SpreadsheetId.from_url(url)
    except InvalidIdentifierError:
        return
    require(_SPREADSHEET_KEY.fullmatch(sid.value) is not None, f"bad key {sid.value!r}")
    require(f"/spreadsheets/d/{sid.value}" in url, f"{sid.value!r} not taken from {url!r}")


def check_spreadsheet_id_round_trip(key: str) -> None:
    """A key embedded in a standard Sheets URL is extracted unchanged."""
    if _SPREADSHEET_KEY.fullmatch(key) is None:
        return
    for url in (
        f"https://docs.google.com/spreadsheets/d/{key}/edit#gid=0",
        f"https://docs.google.com/spreadsheets/d/{key}",
    ):
        value = SpreadsheetId.from_url(url).value
        require(value == key, f"from_url({url!r}) = {value!r}")
