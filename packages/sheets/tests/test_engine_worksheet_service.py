"""Tests aislados de ``WorksheetService`` con hoja/documento falsos (sin gspread real)."""

from typing import Any
from unittest.mock import Mock

import pytest
from gspreadmanager.application.worksheet_service import WorksheetService
from gspreadmanager.domain.values import Color, GridRange


@pytest.fixture
def service():
    return WorksheetService()


def test_create(service):
    spreadsheet = Mock()
    result = service.create(spreadsheet, "Nueva", 100, 26, None)
    spreadsheet.add_worksheet.assert_called_once_with("Nueva", 100, 26, None)
    assert result is spreadsheet.add_worksheet.return_value


def test_delete(service):
    spreadsheet = Mock()
    service.delete(spreadsheet, "Vieja")
    spreadsheet.delete_worksheet.assert_called_once_with("Vieja")


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
    ws.find.assert_called_once_with("Total", True)
    assert result is ws.find.return_value


class TestDimensions:
    def _ws(self) -> Any:
        ws = Mock()
        ws.id = 5
        return ws

    def _request(self, ws: Any) -> Any:
        return ws.spreadsheet.batch_update.call_args[0][0]["requests"][0]

    def test_insert_dimension(self):
        ws = self._ws()
        WorksheetService().insert_dimension(ws, "ROWS", 2, 4, False)
        assert self._request(ws) == {
            "insertDimension": {
                "range": {"sheetId": 5, "dimension": "ROWS", "startIndex": 2, "endIndex": 4},
                "inheritFromBefore": False,
            }
        }

    def test_delete_dimension(self):
        ws = self._ws()
        WorksheetService().delete_dimension(ws, "COLUMNS", 0, 3)
        assert self._request(ws) == {
            "deleteDimension": {
                "range": {"sheetId": 5, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 3}
            }
        }

    def test_append_dimension(self):
        ws = self._ws()
        WorksheetService().append_dimension(ws, "ROWS", 10)
        assert self._request(ws) == {
            "appendDimension": {"sheetId": 5, "dimension": "ROWS", "length": 10}
        }

    def test_update_dimension(self):
        ws = self._ws()
        WorksheetService().update_dimension(
            ws, "ROWS", 0, 2, {"hiddenByUser": True}, "hiddenByUser"
        )
        assert self._request(ws) == {
            "updateDimensionProperties": {
                "range": {"sheetId": 5, "dimension": "ROWS", "startIndex": 0, "endIndex": 2},
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }


class TestSortFilterMergeTab:
    def _ws(self) -> Any:
        ws = Mock()
        ws.id = 7
        return ws

    def _request(self, ws: Any) -> Any:
        return ws.spreadsheet.batch_update.call_args[0][0]["requests"][0]

    def _grid(self) -> GridRange:
        return GridRange(sheet_id=7, start_row_index=0, end_row_index=10)

    def test_sort_range(self):
        ws = self._ws()
        specs = [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}]
        WorksheetService().sort_range(ws, self._grid(), specs)
        assert self._request(ws) == {
            "sortRange": {
                "range": {"sheetId": 7, "startRowIndex": 0, "endRowIndex": 10},
                "sortSpecs": specs,
            }
        }

    def test_set_basic_filter_with_range(self):
        ws = self._ws()
        WorksheetService().set_basic_filter(ws, self._grid())
        assert self._request(ws) == {
            "setBasicFilter": {
                "filter": {"range": {"sheetId": 7, "startRowIndex": 0, "endRowIndex": 10}}
            }
        }

    def test_set_basic_filter_whole_sheet(self):
        ws = self._ws()
        WorksheetService().set_basic_filter(ws, None)
        assert self._request(ws) == {"setBasicFilter": {"filter": {"range": {"sheetId": 7}}}}

    def test_clear_basic_filter(self):
        ws = self._ws()
        WorksheetService().clear_basic_filter(ws)
        assert self._request(ws) == {"clearBasicFilter": {"sheetId": 7}}

    def test_unmerge(self):
        ws = self._ws()
        WorksheetService().unmerge(ws, self._grid())
        assert self._request(ws) == {
            "unmergeCells": {"range": {"sheetId": 7, "startRowIndex": 0, "endRowIndex": 10}}
        }

    def test_set_tab_color(self):
        ws = self._ws()
        color = Color(1.0, 0.0, 0.0)
        WorksheetService().set_tab_color(ws, color)
        assert self._request(ws) == {
            "updateSheetProperties": {
                "properties": {"sheetId": 7, "tabColor": color.to_dict()},
                "fields": "tabColor",
            }
        }

    def test_clear_tab_color(self):
        ws = self._ws()
        WorksheetService().clear_tab_color(ws)
        assert self._request(ws) == {
            "updateSheetProperties": {"properties": {"sheetId": 7}, "fields": "tabColor"}
        }
