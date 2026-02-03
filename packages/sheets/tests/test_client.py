"""Tests for Sheets client."""

from unittest.mock import Mock, patch

import pytest

from gsuite_sheets.client import Sheets
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet


class TestSheetsInit:
    """Tests for Sheets client initialization."""

    def test_init_with_auth(self):
        """Test Sheets client initialization."""
        mock_auth = Mock()
        sheets = Sheets(mock_auth)

        assert sheets.auth is mock_auth
        assert sheets._sheets_service is None
        assert sheets._drive_service is None


class TestSheetsService:
    """Tests for Sheets service properties."""

    @patch("gsuite_sheets.client.build")
    def test_lazy_sheets_service(self, mock_build):
        """Test Sheets service is created lazily."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)

        mock_build.assert_not_called()

        service = sheets.service

        mock_build.assert_called_once_with("sheets", "v4", credentials=mock_auth.credentials)
        assert service is mock_service

    @patch("gsuite_sheets.client.build")
    def test_lazy_drive_service(self, mock_build):
        """Test Drive service is created lazily."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)

        drive = sheets.drive

        mock_build.assert_called_once_with("drive", "v3", credentials=mock_auth.credentials)
        assert drive is mock_service


class TestOpen:
    """Tests for open methods."""

    @patch("gsuite_sheets.client.build")
    def test_open_by_title(self, mock_build):
        """Test opening spreadsheet by title."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_drive = Mock()
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "sheet123", "name": "Test Sheet"}]
        }

        mock_sheets = Mock()
        mock_sheets.spreadsheets().get().execute.return_value = {
            "spreadsheetId": "sheet123",
            "properties": {"title": "Test Sheet"},
            "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}}],
        }

        mock_build.side_effect = [mock_sheets, mock_drive]

        sheets = Sheets(mock_auth)
        spreadsheet = sheets.open("Test Sheet")

        assert isinstance(spreadsheet, Spreadsheet)
        assert spreadsheet.title == "Test Sheet"

    @patch("gsuite_sheets.client.build")
    def test_open_not_found(self, mock_build):
        """Test opening non-existent spreadsheet."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_drive = Mock()
        mock_drive.files().list().execute.return_value = {"files": []}
        mock_build.return_value = mock_drive

        sheets = Sheets(mock_auth)

        with pytest.raises(ValueError, match="not found"):
            sheets.open("Nonexistent")

    @patch("gsuite_sheets.client.build")
    def test_open_by_key(self, mock_build):
        """Test opening spreadsheet by key."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().get().execute.return_value = {
            "spreadsheetId": "abc123",
            "properties": {"title": "My Sheet"},
            "sheets": [],
        }
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        spreadsheet = sheets.open_by_key("abc123")

        assert spreadsheet.id == "abc123"

    @patch.object(Sheets, "open_by_key")
    def test_open_by_url(self, mock_open):
        """Test opening spreadsheet by URL."""
        mock_auth = Mock()
        sheets = Sheets(mock_auth)

        mock_open.return_value = Mock(spec=Spreadsheet)

        sheets.open_by_url("https://docs.google.com/spreadsheets/d/abc123/edit")

        mock_open.assert_called_once_with("abc123")

    def test_open_by_url_invalid(self):
        """Test opening with invalid URL."""
        mock_auth = Mock()
        sheets = Sheets(mock_auth)

        with pytest.raises(ValueError, match="Invalid"):
            sheets.open_by_url("https://example.com/not-a-sheet")


class TestCreate:
    """Tests for create method."""

    @patch("gsuite_sheets.client.build")
    def test_create_spreadsheet(self, mock_build):
        """Test creating a new spreadsheet."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().create().execute.return_value = {
            "spreadsheetId": "new123",
            "properties": {"title": "New Spreadsheet"},
            "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}}],
        }
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        spreadsheet = sheets.create("New Spreadsheet")

        assert isinstance(spreadsheet, Spreadsheet)
        assert spreadsheet.id == "new123"
        assert spreadsheet.title == "New Spreadsheet"


class TestListSpreadsheets:
    """Tests for list_spreadsheets method."""

    @patch("gsuite_sheets.client.build")
    def test_list_spreadsheets(self, mock_build):
        """Test listing spreadsheets."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_drive = Mock()
        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "sheet1", "name": "Sheet 1"},
                {"id": "sheet2", "name": "Sheet 2"},
            ]
        }
        mock_build.return_value = mock_drive

        sheets = Sheets(mock_auth)
        result = sheets.list_spreadsheets()

        assert len(result) == 2
        assert result[0]["name"] == "Sheet 1"


class TestValueOperations:
    """Tests for value operations."""

    @patch("gsuite_sheets.client.build")
    def test_get_values(self, mock_build):
        """Test getting values from a range."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [["A1", "B1"], ["A2", "B2"]]
        }
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        values = sheets.get_values("sheet123", "A1:B2")

        assert values == [["A1", "B1"], ["A2", "B2"]]

    @patch("gsuite_sheets.client.build")
    def test_get_values_empty(self, mock_build):
        """Test getting values from empty range."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().values().get().execute.return_value = {}
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        values = sheets.get_values("sheet123", "A1:B2")

        assert values == []

    @patch("gsuite_sheets.client.build")
    def test_update_values(self, mock_build):
        """Test updating values."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        sheets.update_values("sheet123", "A1:B2", [["New", "Values"]])

        call_args = mock_service.spreadsheets().values().update.call_args
        assert call_args[1]["valueInputOption"] == "USER_ENTERED"

    @patch("gsuite_sheets.client.build")
    def test_append_values(self, mock_build):
        """Test appending values."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        sheets.append_values("sheet123", "A:A", [["New Row"]])

        call_args = mock_service.spreadsheets().values().append.call_args
        assert call_args[1]["insertDataOption"] == "INSERT_ROWS"

    @patch("gsuite_sheets.client.build")
    def test_clear_values(self, mock_build):
        """Test clearing values."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        sheets.clear_values("sheet123", "A1:B10")

        mock_service.spreadsheets().values().clear.assert_called()


class TestWorksheetOperations:
    """Tests for worksheet operations."""

    @patch("gsuite_sheets.client.build")
    def test_add_worksheet(self, mock_build):
        """Test adding a worksheet."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": 123,
                            "title": "New Sheet",
                            "index": 1,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": 26,
                            },
                        },
                    },
                }
            ],
        }
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        ws = sheets.add_worksheet("sheet123", "New Sheet")

        assert isinstance(ws, Worksheet)
        assert ws.title == "New Sheet"
        assert ws.id == 123

    @patch("gsuite_sheets.client.build")
    def test_delete_worksheet(self, mock_build):
        """Test deleting a worksheet."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        result = sheets.delete_worksheet("sheet123", 456)

        assert result is True

    @patch("gsuite_sheets.client.build")
    def test_delete_worksheet_failure(self, mock_build):
        """Test worksheet deletion failure."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.spreadsheets().batchUpdate().execute.side_effect = Exception("Error")
        mock_build.return_value = mock_service

        sheets = Sheets(mock_auth)
        result = sheets.delete_worksheet("sheet123", 456)

        assert result is False


class TestShare:
    """Tests for share method."""

    @patch("gsuite_sheets.client.build")
    def test_share_success(self, mock_build):
        """Test successful sharing."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_drive = Mock()
        mock_build.return_value = mock_drive

        sheets = Sheets(mock_auth)
        result = sheets.share("sheet123", "user@example.com", role="writer")

        assert result is True

        call_args = mock_drive.permissions().create.call_args
        assert call_args[1]["body"]["emailAddress"] == "user@example.com"
        assert call_args[1]["body"]["role"] == "writer"

    @patch("gsuite_sheets.client.build")
    def test_share_failure(self, mock_build):
        """Test share failure."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_drive = Mock()
        mock_drive.permissions().create().execute.side_effect = Exception("Error")
        mock_build.return_value = mock_drive

        sheets = Sheets(mock_auth)
        result = sheets.share("sheet123", "user@example.com")

        assert result is False


class TestParseSpreadsheet:
    """Tests for spreadsheet parsing."""

    def test_parse_spreadsheet(self):
        """Test parsing spreadsheet data."""
        mock_auth = Mock()
        sheets = Sheets(mock_auth)

        data = {
            "spreadsheetId": "abc123",
            "properties": {
                "title": "Test Sheet",
                "locale": "en_US",
                "timeZone": "America/Buenos_Aires",
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
                {
                    "properties": {
                        "sheetId": 1,
                        "title": "Sheet2",
                        "index": 1,
                        "gridProperties": {
                            "rowCount": 500,
                            "columnCount": 10,
                        },
                    },
                },
            ],
        }

        spreadsheet = sheets._parse_spreadsheet(data)

        assert spreadsheet.id == "abc123"
        assert spreadsheet.title == "Test Sheet"
        assert spreadsheet.time_zone == "America/Buenos_Aires"
        assert len(spreadsheet.worksheets) == 2
        assert spreadsheet.worksheets[0].title == "Sheet1"
        assert spreadsheet.worksheets[1].row_count == 500
