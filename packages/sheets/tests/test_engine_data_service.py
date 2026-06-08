"""Tests aislados de ``DataService`` con hoja/documento falsos (sin gspread real)."""

from unittest.mock import Mock

import pytest
from gspreadmanager.application.data_service import DataService
from gspreadmanager.domain.errors import InsertError


@pytest.fixture
def service():
    return DataService()


def test_update_cell(service):
    ws = Mock()
    service.update_cell(ws, 2, 3, "x")
    ws.update_cell.assert_called_once_with(2, 3, "x")


def test_update_row_starts_at_column(service):
    ws = Mock()
    service.update_row(ws, 5, ["a", "b"], start_column=2)
    assert [c.args for c in ws.update_cell.call_args_list] == [(5, 2, "a"), (5, 3, "b")]


def test_read_values_skiprows(service):
    ws = Mock()
    ws.get_all_values.return_value = [["h"], ["1"], ["2"]]
    assert service.read_values(ws, skiprows=1) == [["1"], ["2"]]


def test_as_dicts(service):
    rows = [["name", "age"], ["Ana", "3"], ["Bob", "4"]]
    assert service.as_dicts(rows) == [{"name": "Ana", "age": "3"}, {"name": "Bob", "age": "4"}]


def test_as_dicts_empty(service):
    assert service.as_dicts([]) == []


def test_last_row(service):
    ws = Mock()
    ws.get_all_values.return_value = [["h"], ["a"], ["b"]]
    assert service.last_row(ws) == 3


def test_rows_where_column_equals(service):
    ws = Mock()
    ws.get_all_values.return_value = [
        ["Name", "Status"],
        ["Ana", "Active"],
        ["Bob", "Inactive"],
        ["Cris", "Active"],
    ]
    result = service.rows_where_column_equals(ws, 1, "Active")
    assert result == [(2, ["Ana", "Active"]), (4, ["Cris", "Active"])]


def test_append_forwards_value_input_option(service):
    ws = Mock()
    service.append(ws, [["a"]], "RAW")
    ws.append_rows.assert_called_once_with([["a"]], "RAW")


def test_batch_update_forwards(service):
    ws = Mock()
    service.batch_update(ws, [{"range": "A1", "values": [["x"]]}], "RAW")
    ws.batch_update.assert_called_once_with([{"range": "A1", "values": [["x"]]}], "RAW")


def test_read_range_numbers_rows(service):
    spreadsheet = Mock()
    spreadsheet.values_get.return_value = {"values": [["a"], ["b"]]}
    assert service.read_range(spreadsheet, "Hoja1!A1:A2", 1) == [
        {"fila": 1, "values": ["a"]},
        {"fila": 2, "values": ["b"]},
    ]


def test_read_range_without_values(service):
    spreadsheet = Mock()
    spreadsheet.values_get.return_value = {}
    assert service.read_range(spreadsheet, "Hoja1!A1:A2", 1) == []


def test_row_with_empty_in_column_found(service):
    ws = Mock()
    ws.col_values.return_value = ["a", "b", "c"]
    ws.range.return_value = [Mock(value="x"), Mock(value=""), Mock(value="z")]
    ws.row_values.return_value = ["row2"]
    assert service.row_with_empty_in_column(ws, "B") == (["row2"], 2)


def test_row_with_empty_in_column_none(service):
    ws = Mock()
    ws.col_values.return_value = ["a", "b"]
    ws.range.return_value = [Mock(value="x"), Mock(value="y")]
    assert service.row_with_empty_in_column(ws, "B") == (None, None)


def test_insert_not_list_of_lists(service):
    with pytest.raises(ValueError, match="lista de listas"):
        service.insert(Mock(), "Hoja1", ["a", "b"])


def test_insert_uneven_rows(service):
    with pytest.raises(ValueError, match="misma longitud"):
        service.insert(Mock(), "Hoja1", [["a", "b"], ["c"]])


def test_insert_appends_at_end_when_no_row(service):
    ws = Mock()
    ws.get_all_values.return_value = [["h"], ["1"]]  # 2 filas -> inserta en la 3
    service.insert(ws, "Hoja1", [["a", "b"]])
    args = ws.spreadsheet.values_append.call_args[0]
    assert args[0] == "Hoja1!A3:B3"
    assert args[2] == {"values": [["a", "b"]]}


def test_insert_wraps_errors(service):
    ws = Mock()
    ws.spreadsheet.values_append.side_effect = RuntimeError("boom")
    with pytest.raises(InsertError, match="Error al insertar"):
        service.insert(ws, "Hoja1", [["a"]], first_row=1)
