"""Tests for Sheets parser."""

import pytest

from gsuite_sheets.parser import SheetsParser


class TestSheetsParser:
    """Tests for SheetsParser."""

    def test_parse_spreadsheet_basic(self):
        """Test parsing a basic spreadsheet."""
        data = {
            "spreadsheetId": "abc123",
            "properties": {
                "title": "My Spreadsheet",
                "locale": "en_US",
                "timeZone": "America/New_York",
            },
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "index": 0,
                        "gridProperties": {
                            "rowCount": 1000,
                            "columnCount": 26,
                        },
                    },
                },
            ],
        }

        spreadsheet = SheetsParser.parse_spreadsheet(data)

        assert spreadsheet.id == "abc123"
        assert spreadsheet.title == "My Spreadsheet"
        assert spreadsheet.locale == "en_US"
        assert len(spreadsheet.worksheets) == 1
        assert spreadsheet.worksheets[0].title == "Sheet1"

    def test_parse_spreadsheet_multiple_sheets(self):
        """Test parsing spreadsheet with multiple worksheets."""
        data = {
            "spreadsheetId": "xyz789",
            "properties": {"title": "Multi Sheet"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Data",
                        "index": 0,
                        "gridProperties": {"rowCount": 100, "columnCount": 10},
                    },
                },
                {
                    "properties": {
                        "sheetId": 1,
                        "title": "Summary",
                        "index": 1,
                        "gridProperties": {"rowCount": 50, "columnCount": 5},
                    },
                },
            ],
        }

        spreadsheet = SheetsParser.parse_spreadsheet(data)

        assert len(spreadsheet.worksheets) == 2
        assert spreadsheet.worksheets[0].title == "Data"
        assert spreadsheet.worksheets[0].row_count == 100
        assert spreadsheet.worksheets[1].title == "Summary"
        assert spreadsheet.worksheets[1].column_count == 5

    def test_parse_worksheet(self):
        """Test parsing a worksheet."""
        data = {
            "properties": {
                "sheetId": 123,
                "title": "Test Sheet",
                "index": 2,
                "gridProperties": {
                    "rowCount": 500,
                    "columnCount": 20,
                },
            },
        }

        worksheet = SheetsParser.parse_worksheet(data)

        assert worksheet.id == 123
        assert worksheet.title == "Test Sheet"
        assert worksheet.index == 2
        assert worksheet.row_count == 500
        assert worksheet.column_count == 20

    def test_parse_worksheet_from_reply(self):
        """Test parsing worksheet from addSheet reply."""
        data = {
            "properties": {
                "sheetId": 456,
                "title": "New Sheet",
                "index": 0,
                "gridProperties": {
                    "rowCount": 1000,
                    "columnCount": 26,
                },
            },
        }

        worksheet = SheetsParser.parse_worksheet_from_reply(data)

        assert worksheet.id == 456
        assert worksheet.title == "New Sheet"

    def test_parse_spreadsheet_url_generation(self):
        """Test that URL is correctly generated."""
        data = {
            "spreadsheetId": "test_id_123",
            "properties": {"title": "Test"},
            "sheets": [],
        }

        spreadsheet = SheetsParser.parse_spreadsheet(data)

        assert "test_id_123" in spreadsheet.url
        assert spreadsheet.url.startswith("https://docs.google.com/spreadsheets/d/")
