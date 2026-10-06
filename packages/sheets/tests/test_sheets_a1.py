"""A1 notation helpers."""

import pytest

from gsuite_core.exceptions import ValidationError
from gsuite_sheets.a1 import a1, column_index, column_letter, grid_range, quote_title


@pytest.mark.parametrize(
    ("title", "quoted"),
    [
        ("Sheet1", "'Sheet1'"),
        ("Q1 Budget", "'Q1 Budget'"),
        ("Pablo's", "'Pablo''s'"),
        ("2024", "'2024'"),
    ],
)
def test_quote_title(title, quoted):
    assert quote_title(title) == quoted


def test_a1():
    assert a1("Data", "A1:B2") == "'Data'!A1:B2"
    assert a1("Data") == "'Data'"


@pytest.mark.parametrize(
    ("letters", "index"), [("A", 0), ("Z", 25), ("AA", 26), ("ZZ", 701), ("AAA", 702), ("b", 1)]
)
def test_columns_round_trip(letters, index):
    assert column_index(letters) == index
    assert column_letter(index) == letters.upper()


@pytest.mark.parametrize(
    ("cell_range", "expected"),
    [
        ("B2", {"startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 1, "endColumnIndex": 2}),
        (
            "A1:C10",
            {"startRowIndex": 0, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 3},
        ),
        ("A:C", {"startColumnIndex": 0, "endColumnIndex": 3}),
        ("1:5", {"startRowIndex": 0, "endRowIndex": 5}),
        ("A2:C", {"startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 3}),
    ],
)
def test_grid_range(cell_range, expected):
    assert grid_range(cell_range, sheet_id=7) == {"sheetId": 7, **expected}


@pytest.mark.parametrize("bad", ["", "A1:", "1A", "A0", "A1:B2:C3", "Sheet1!"])
def test_invalid_ranges(bad):
    with pytest.raises(ValidationError):
        grid_range(bad, 0)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("'Q1 Budget'!A1:B2", ("Q1 Budget", "A1:B2")),
        ("'Pablo''s'!C3", ("Pablo's", "C3")),
        ("'Wow!'!A1", ("Wow!", "A1")),
        ("'Data'", ("Data", None)),
        ("Data!A:A", ("Data", "A:A")),
        ("B2", (None, "B2")),
    ],
)
def test_split_sheet(reference, expected):
    from gsuite_sheets.a1 import split_sheet

    assert split_sheet(reference) == expected


def test_grid_range_ignores_sheet_prefix():
    assert grid_range("'Wow!'!B2:C3", 4) == grid_range("B2:C3", 4)


def test_engine_grid_range_delegates_here():
    """One A1 implementation: the engine's GridRange.from_a1 uses this module."""
    from gsuite_sheets.engine.domain.errors import InvalidRangeError
    from gsuite_sheets.engine.domain.values import GridRange

    assert GridRange.from_a1("A2:C", 0).to_dict() == grid_range(
        "A2:C", 0
    )  # engine used to drop row 2
    with pytest.raises(InvalidRangeError):
        GridRange.from_a1("A1:", 0)  # engine used to accept it as A1
