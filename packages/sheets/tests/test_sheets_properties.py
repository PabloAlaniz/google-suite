"""Property-based tests for A1 notation, colors, numericise, schema, batching and ranges.

The invariants live in ``gsuite_sheets._testing.properties`` so the fuzz harnesses
check exactly the same properties. Known bugs are strict xfails with an explicit
``@example``: fixing a bug flips exactly its test.
"""

import string

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_sheets._testing.properties import (
    COERCE_TYPES,
    MAX_COLUMNS,
    check_a1_split_round_trip,
    check_a1range_agrees_with_grid_range,
    check_coerce,
    check_color_from_hex,
    check_column_round_trip,
    check_grid_range,
    check_grid_range_overlaps,
    check_grid_range_total,
    check_numericise,
    check_schema_round_trip,
    check_split_range_data,
    check_split_rows,
    check_split_sheet_lossless,
    check_spreadsheet_id_from_url,
    check_spreadsheet_id_round_trip,
)
from gsuite_sheets.a1 import column_letter, quote_title
from gsuite_sheets.engine.domain.numericise import numericise
from gsuite_sheets.engine.domain.values.ranges import _A1_PATTERN

# --- strategies ------------------------------------------------------------------

columns = st.integers(0, MAX_COLUMNS - 1)
rows = st.integers(1, 10_000)
column_letters = columns.map(column_letter)
a1_alphabet = st.text(alphabet="ABZaz0129:!'", max_size=12)
non_ascii_digits = st.characters(categories=["Nd"]).filter(lambda c: not c.isascii())
hex_digits = st.sampled_from("0123456789abcdefABCDEF")


@st.composite
def valid_ranges(draw: st.DrawFn) -> str:
    """Well-formed, ordered A1 ranges within Sheets' limits."""
    c1, c2 = sorted(draw(st.lists(columns, min_size=2, max_size=2)))
    r1, r2 = sorted(draw(st.lists(rows, min_size=2, max_size=2)))
    l1, l2 = column_letter(c1), column_letter(c2)
    shape = draw(st.sampled_from(["cell", "cells", "cols", "rows", "open"]))
    return {
        "cell": f"{l1}{r1}",
        "cells": f"{l1}{r1}:{l2}{r2}",
        "cols": f"{l1}:{l2}",
        "rows": f"{r1}:{r2}",
        "open": f"{l1}{r1}:{l2}",
    }[shape]


@st.composite
def reversed_ranges(draw: st.DrawFn) -> str:
    """Ranges whose end precedes their start on at least one axis."""
    c1, c2 = draw(columns), draw(columns)
    r1, r2 = draw(rows), draw(rows)
    if c1 <= c2 and r1 <= r2:
        r1, r2 = r2 + 1, r1
    return f"{column_letter(c1)}{r1}:{column_letter(c2)}{r2}"


# --- A1 notation -------------------------------------------------------------------


@given(columns)
def test_column_letter_round_trip(index):
    check_column_round_trip(index)


@given(st.text(max_size=20), st.one_of(st.none(), st.text(min_size=1, max_size=12)))
def test_split_sheet_inverts_a1(title, cell_range):
    check_a1_split_round_trip(title, cell_range)


@given(
    st.one_of(
        st.builds(
            lambda t, r: quote_title(t) + r,
            st.text(max_size=10),
            st.just("") | st.text(max_size=8).map("!".__add__),
        ),
        st.text(max_size=20).filter(lambda s: not s.startswith("'")),
    )
)
def test_split_sheet_well_formed_is_lossless(reference):
    check_split_sheet_lossless(reference)


@pytest.mark.xfail(strict=True, reason="B6: split_sheet drops text after a quoted title")
@given(
    st.builds(
        lambda t, junk: quote_title(t) + junk,
        st.text(max_size=8),
        st.text(min_size=1, max_size=8).filter(lambda s: s[0] not in "!'"),
    )
)
@example("'a'b!C1")
def test_split_sheet_rejects_text_after_quoted_title(reference):
    check_split_sheet_lossless(reference)


@pytest.mark.xfail(strict=True, reason="B6: split_sheet accepts an unterminated quote")
@given(st.text(alphabet=st.characters(exclude_characters="'"), max_size=10).map("'".__add__))
@example("'abc")
def test_split_sheet_rejects_unterminated_quote(reference):
    check_split_sheet_lossless(reference)


@given(st.one_of(st.text(max_size=16), a1_alphabet), st.integers(0, 2**31))
def test_grid_range_only_raises_validation_error(cell_range, sheet_id):
    check_grid_range_total(cell_range, sheet_id)


@given(valid_ranges(), st.integers(0, 2**31))
def test_grid_range_of_valid_ranges(cell_range, sheet_id):
    check_grid_range(cell_range, sheet_id)


@given(st.text(max_size=8), valid_ranges())
def test_grid_range_ignores_sheet_prefix(title, cell_range):
    check_grid_range(f"{quote_title(title)}!{cell_range}")


@pytest.mark.xfail(strict=True, reason="B6: grid_range accepts reversed ranges (end < start)")
@given(reversed_ranges())
@example("B5:A1")
def test_grid_range_rejects_or_normalizes_reversed(cell_range):
    check_grid_range(cell_range)


@pytest.mark.xfail(strict=True, reason="B6: grid_range accepts non-ASCII digits as row numbers")
@given(column_letters, st.text(non_ascii_digits, min_size=1, max_size=3))
@example("A", "\u0661")  # ARABIC-INDIC DIGIT ONE
def test_grid_range_rejects_unicode_digits(letters, digits):
    check_grid_range(f"{letters}{digits}")


@pytest.mark.xfail(strict=True, reason="B6: grid_range accepts columns beyond ZZZ")
@given(st.text(alphabet=string.ascii_uppercase, min_size=4, max_size=20), rows)
@example("A" * 20, 1)
def test_grid_range_rejects_columns_beyond_zzz(letters, row):
    check_grid_range(f"{letters}{row}")


@given(st.one_of(st.from_regex(_A1_PATTERN, fullmatch=True), a1_alphabet))
def test_a1range_and_grid_range_agree(cell_range):
    check_a1range_agrees_with_grid_range(cell_range)


# --- Color.from_hex ------------------------------------------------------------------


@given(st.from_regex(r"#?[0-9A-Fa-f]{6}", fullmatch=True))
def test_color_from_valid_hex(hex_color):
    check_color_from_hex(hex_color)


@given(st.text(max_size=10).filter(lambda s: len(s.lstrip("#")) != 6))
def test_color_from_hex_wrong_length(hex_color):
    check_color_from_hex(hex_color)


@pytest.mark.xfail(strict=True, reason="B5: non-hex digits raise ValueError, not InvalidColorError")
@given(
    st.text(alphabet=string.ascii_letters + string.digits, min_size=6, max_size=6).filter(
        lambda s: any(c not in string.hexdigits for c in s)
    )
)
@example("GGGGGG")
def test_color_from_hex_non_hex_raises_invalid_color(hex_color):
    check_color_from_hex(hex_color)


@pytest.mark.xfail(strict=True, reason="B5: from_hex accepts signed components ('+1+2+3')")
@given(st.lists(st.tuples(st.sampled_from("+-"), hex_digits).map("".join), min_size=3, max_size=3))
@example(["+1", "+2", "+3"])
def test_color_from_hex_rejects_signs(pairs):
    check_color_from_hex("".join(pairs))


@pytest.mark.xfail(strict=True, reason="B5: from_hex accepts fullwidth digits")
@given(st.text(non_ascii_digits, min_size=6, max_size=6))
@example("\uff11\uff12\uff13\uff14\uff15\uff16")  # fullwidth "123456"
def test_color_from_hex_rejects_unicode_digits(hex_color):
    check_color_from_hex(hex_color)


@pytest.mark.xfail(strict=True, reason="B9-sheets-1: from_hex strips any number of '#'")
@given(st.integers(2, 5), st.from_regex(r"[0-9A-Fa-f]{6}", fullmatch=True))
@example(2, "123456")
def test_color_from_hex_rejects_repeated_hash(hashes, digits):
    check_color_from_hex("#" * hashes + digits)


@pytest.mark.xfail(strict=True, reason="B9-sheets-2: from_hex accepts whitespace (' 12345')")
@given(
    st.lists(
        st.tuples(st.sampled_from(" \t\n"), hex_digits, st.booleans()).map(
            lambda t: t[0] + t[1] if t[2] else t[1] + t[0]
        ),
        min_size=3,
        max_size=3,
    )
)
@example([" 1", "23", "45"])
def test_color_from_hex_rejects_whitespace(pairs):
    check_color_from_hex("".join(pairs))


# --- numericise ----------------------------------------------------------------------


@given(st.integers(-(10**30), 10**30))
def test_numericise_integers(number):
    check_numericise(str(number))


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_numericise_floats(number):
    check_numericise(repr(number))


@given(st.text(alphabet=string.digits, min_size=1, max_size=10).map("0".__add__))
def test_numericise_keeps_leading_zeros(digits):
    check_numericise(digits)


@given(
    st.text(alphabet=string.ascii_letters + string.digits + ".", max_size=10).filter(
        lambda s: s.lower() not in {"nan", "inf", "infinity"}
    )
)
def test_numericise_ascii_text(value):
    check_numericise(value)


@given(st.one_of(st.none(), st.integers(), st.floats(), st.booleans()))
def test_numericise_passes_non_strings_through(value):
    assert numericise(value) is value


@pytest.mark.xfail(strict=True, reason="B8: signed leading zeros are lost ('-007' -> -7)")
@given(st.sampled_from("+-"), st.text(alphabet=string.digits, min_size=1, max_size=6))
@example("-", "07")
def test_numericise_keeps_signed_leading_zeros(sign, digits):
    check_numericise(f"{sign}0{digits}")


@pytest.mark.xfail(strict=True, reason="B8: underscores are parsed as digit separators")
@given(st.lists(st.integers(1, 999).map(str), min_size=2, max_size=4))
@example(["1", "000"])
def test_numericise_keeps_underscored_numbers(groups):
    check_numericise("_".join(groups))


@pytest.mark.xfail(strict=True, reason="B8: 'nan'/'inf' become non-finite floats")
@given(st.sampled_from(["nan", "NaN", "inf", "-inf", "Infinity", "+infinity"]))
@example("nan")
def test_numericise_keeps_nan_and_inf_text(value):
    check_numericise(value)


@pytest.mark.xfail(strict=True, reason="B8: non-ASCII digits are parsed (U+0663 -> 3)")
@given(st.text(non_ascii_digits, min_size=1, max_size=4))
@example("\u0663")  # ARABIC-INDIC DIGIT THREE
def test_numericise_keeps_unicode_digits(value):
    check_numericise(value)


@pytest.mark.xfail(strict=True, reason="B9-sheets-3: padded leading zeros are lost (' 007' -> 7)")
@given(st.sampled_from([" ", "\t", "\n"]), st.text(alphabet=string.digits, min_size=1, max_size=6))
@example(" ", "07")
def test_numericise_keeps_padded_leading_zeros(pad, digits):
    check_numericise(f"{pad}0{digits}")


# --- schema ----------------------------------------------------------------------------

records = st.tuples(
    st.text(max_size=10),
    st.integers(-(10**18), 10**18),
    st.floats(),
    st.booleans(),
    st.dates(),
    st.none() | st.text(max_size=10),
    st.none() | st.integers(-(10**9), 10**9),
)


@given(st.lists(records, max_size=4))
def test_schema_round_trip(items):
    check_schema_round_trip(items)


@given(
    st.one_of(
        st.text(max_size=12),
        st.sampled_from(["", "1", "-2", "1.5", "nan", "TRUE", "x", "2024-02-30", "low", "a"]),
    ),
    st.sampled_from(sorted(COERCE_TYPES)),
)
def test_coerce_only_raises_schema_error(value, kind):
    check_coerce(value, kind)


# --- batching ----------------------------------------------------------------------------

sheet_rows = st.lists(st.lists(st.integers(0, 9), max_size=6), max_size=12)
max_cells = st.none() | st.integers(-1, 20)


@given(sheet_rows, max_cells)
def test_split_rows(items, cap):
    check_split_rows(items, cap)


@given(
    st.lists(
        st.builds(lambda r, v: {"range": r, "values": v}, st.text(max_size=4), sheet_rows)
        | st.builds(lambda r: {"range": r}, st.text(max_size=4)),
        max_size=8,
    ),
    max_cells,
)
def test_split_range_data(items, cap):
    check_split_range_data(items, cap)


# --- GridRange.overlaps / SpreadsheetId ------------------------------------------------


@st.composite
def axis(draw: st.DrawFn, *, allow_empty: bool = False) -> tuple[int | None, int | None]:
    start = draw(st.none() | st.integers(0, 6))
    low = start or 0
    end = draw(st.none() | st.integers(low if allow_empty else low + 1, 8))
    return start, end


bounds = st.builds(lambda r, c: (*r, *c), axis(), axis())


@given(bounds, bounds)
def test_overlaps_matches_cell_intersection(first, second):
    check_grid_range_overlaps(first, second)


@pytest.mark.xfail(strict=True, reason="B9-sheets-4: an empty GridRange (start == end) overlaps")
@given(st.integers(0, 6), bounds)
@example(2, (0, 5, 0, 5))
def test_empty_grid_range_overlaps_nothing(edge, other):
    check_grid_range_overlaps((edge, edge, None, None), other)


@given(
    st.one_of(
        st.text(max_size=30),
        st.text(max_size=20).map("https://docs.google.com/spreadsheets/d/".__add__),
    )
)
def test_spreadsheet_id_from_url(url):
    check_spreadsheet_id_from_url(url)


@given(st.from_regex(r"[A-Za-z0-9_-]{1,44}", fullmatch=True))
def test_spreadsheet_id_round_trip(key):
    check_spreadsheet_id_round_trip(key)
