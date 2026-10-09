"""Tests de ``infrastructure.request_builders``: conversión A1 -> GridRange (contra gsuite_sheets.a1)."""

from gsuite_sheets.a1 import grid_range as a1_range_to_grid_range
from gsuite_sheets.engine.infrastructure.request_builders import grid_range


def test_grid_range_matches_gspread_conversion():
    assert grid_range("A1:B5", 7).to_dict() == a1_range_to_grid_range("A1:B5", 7)


def test_grid_range_unbounded_column():
    assert grid_range("A:A", 0).to_dict() == a1_range_to_grid_range("A:A", 0)
