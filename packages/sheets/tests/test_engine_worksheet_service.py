"""Tests aislados de ``WorksheetService`` con hoja/documento falsos (sin gspread real)."""

from unittest.mock import Mock

import pytest
from gspreadmanager.application.worksheet_service import WorksheetService


@pytest.fixture
def service():
    return WorksheetService()


def test_create(service):
    spreadsheet = Mock()
    result = service.create(spreadsheet, "Nueva", 100, 26, None)
    spreadsheet.add_worksheet.assert_called_once_with("Nueva", rows=100, cols=26, index=None)
    assert result is spreadsheet.add_worksheet.return_value


def test_delete(service):
    spreadsheet = Mock()
    ws = Mock()
    spreadsheet.worksheet.return_value = ws
    service.delete(spreadsheet, "Vieja")
    spreadsheet.worksheet.assert_called_once_with("Vieja")
    spreadsheet.del_worksheet.assert_called_once_with(ws)


def test_clear_whole_sheet(service):
    ws = Mock()
    service.clear(ws, None)
    ws.clear.assert_called_once_with()
    ws.batch_clear.assert_not_called()


def test_clear_single_range_normalized_to_list(service):
    ws = Mock()
    service.clear(ws, "A1:C10")
    ws.batch_clear.assert_called_once_with(["A1:C10"])


def test_clear_multiple_ranges(service):
    ws = Mock()
    service.clear(ws, ["A1:A5", "C1:C5"])
    ws.batch_clear.assert_called_once_with(["A1:A5", "C1:C5"])


def test_find(service):
    ws = Mock()
    result = service.find(ws, "Total", True)
    ws.find.assert_called_once_with("Total", case_sensitive=True)
    assert result is ws.find.return_value
