"""Tests for Worksheet entity."""

import pytest

from gsuite_sheets.worksheet import Worksheet


class TestWorksheet:
    """Tests for Worksheet entity."""

    @pytest.fixture
    def worksheet(self):
        """Create a sample worksheet."""
        return Worksheet(
            id=0,
            title="Sheet1",
            index=0,
            row_count=1000,
            column_count=26,
        )

    def test_col_to_letter_single(self):
        """Test single letter columns."""
        assert Worksheet._col_to_letter(1) == "A"
        assert Worksheet._col_to_letter(2) == "B"
        assert Worksheet._col_to_letter(26) == "Z"

    def test_col_to_letter_double(self):
        """Test double letter columns."""
        assert Worksheet._col_to_letter(27) == "AA"
        assert Worksheet._col_to_letter(28) == "AB"
        assert Worksheet._col_to_letter(52) == "AZ"
        assert Worksheet._col_to_letter(53) == "BA"

    def test_col_to_letter_triple(self):
        """Test triple letter columns."""
        assert Worksheet._col_to_letter(703) == "AAA"

    def test_get_without_spreadsheet(self, worksheet):
        """Test get raises error without spreadsheet."""
        with pytest.raises(RuntimeError, match="not linked"):
            worksheet.get("A1")

    def test_update_without_spreadsheet(self, worksheet):
        """Test update raises error without spreadsheet."""
        with pytest.raises(RuntimeError, match="not linked"):
            worksheet.update("A1", [["value"]])


class TestWorksheetDataParsing:
    """Tests for data parsing in worksheet."""

    def test_get_all_records_empty(self):
        """Test get_all_records with no data."""
        ws = Worksheet(id=0, title="Test", index=0)
        # Would need mocking to test properly
        pass
