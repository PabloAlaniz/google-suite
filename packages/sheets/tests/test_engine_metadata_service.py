"""Tests aislados de ``MetadataService`` (notas, named/protected ranges) con fakes."""

from typing import Any
from unittest.mock import Mock

import pytest
from gspreadmanager.application.metadata_service import MetadataService
from gspreadmanager.domain.values import GridRange


@pytest.fixture
def service():
    return MetadataService()


def _request(ws: Any) -> Any:
    return ws.spreadsheet.batch_update.call_args[0][0]["requests"][0]


class TestNotes:
    def test_set_note(self, service):
        ws = Mock()
        grid = GridRange(sheet_id=0, start_row_index=1, end_row_index=2)
        service.set_note(ws, grid, "revisar")
        assert _request(ws) == {
            "updateCells": {
                "range": grid.to_dict(),
                "rows": [{"values": [{"note": "revisar"}]}],
                "fields": "note",
            }
        }

    def test_get_note(self, service):
        ws = Mock()
        ws.spreadsheet.get_metadata.return_value = {
            "sheets": [{"data": [{"rowData": [{"values": [{"note": "hola"}]}]}]}]
        }
        assert service.get_note(ws, "Hoja1!B2") == "hola"
        ws.spreadsheet.get_metadata.assert_called_once_with(
            ["Hoja1!B2"], "sheets(data(rowData(values(note))))"
        )

    def test_get_note_empty(self, service):
        ws = Mock()
        ws.spreadsheet.get_metadata.return_value = {"sheets": [{"data": [{}]}]}
        assert service.get_note(ws, "Hoja1!B2") == ""


class TestNamedRanges:
    def test_define(self, service):
        ws = Mock()
        grid = GridRange(sheet_id=0)
        service.define_named_range(ws, "Total", grid)
        assert _request(ws) == {
            "addNamedRange": {"namedRange": {"name": "Total", "range": grid.to_dict()}}
        }

    def test_list(self, service):
        ss = Mock()
        ss.get_metadata.return_value = {"namedRanges": [{"namedRangeId": "nr1", "name": "Total"}]}
        assert service.list_named_ranges(ss) == [{"namedRangeId": "nr1", "name": "Total"}]
        ss.get_metadata.assert_called_once_with(None, "namedRanges")

    def test_delete(self, service):
        ss = Mock()
        service.delete_named_range(ss, "nr1")
        body = ss.batch_update.call_args[0][0]
        assert body["requests"][0] == {"deleteNamedRange": {"namedRangeId": "nr1"}}


class TestProtectedRanges:
    def test_add(self, service):
        ws = Mock()
        grid = GridRange(sheet_id=0)
        service.add_protected_range(ws, grid, "solo lectura", False)
        assert _request(ws) == {
            "addProtectedRange": {
                "protectedRange": {
                    "range": grid.to_dict(),
                    "warningOnly": False,
                    "description": "solo lectura",
                }
            }
        }

    def test_list_filters_by_sheet(self, service):
        ws = Mock()
        ws.id = 5
        ws.spreadsheet.get_metadata.return_value = {
            "sheets": [
                {"properties": {"sheetId": 9}, "protectedRanges": [{"protectedRangeId": "other"}]},
                {"properties": {"sheetId": 5}, "protectedRanges": [{"protectedRangeId": "pr1"}]},
            ]
        }
        assert service.list_protected_ranges(ws) == [{"protectedRangeId": "pr1"}]

    def test_delete(self, service):
        ss = Mock()
        service.delete_protected_range(ss, "pr1")
        body = ss.batch_update.call_args[0][0]
        assert body["requests"][0] == {"deleteProtectedRange": {"protectedRangeId": "pr1"}}
