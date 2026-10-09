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


@pytest.mark.parametrize("bad", ["", "A1:", "1A", "A0", "Sheet1!A1", "A1:B2:C3"])
def test_invalid_ranges(bad):
    with pytest.raises(ValidationError):
        grid_range(bad, 0)
