"""Tests de ``RowModelService`` con una hoja falsa (sin gspread)."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

from gspreadmanager.application.row_model_service import RowModelService


@dataclass
class Person:
    nombre: str
    edad: int


def _ws(values: list[list[str]]) -> Any:
    ws = Mock()
    ws.get_all_values.return_value = values
    return ws


class TestRead:
    def test_read_maps_rows(self):
        ws = _ws([["nombre", "edad"], ["Ana", "30"]])
        people = RowModelService().read(ws, Person, 0)
        assert people == [Person("Ana", 30)]

    def test_read_empty_sheet_returns_empty(self):
        assert RowModelService().read(_ws([]), Person, 0) == []

    def test_read_skiprows(self):
        ws = _ws([["basura"], ["nombre", "edad"], ["Ana", "30"]])
        assert RowModelService().read(ws, Person, 1) == [Person("Ana", 30)]


class TestAppend:
    def test_append_uses_append_rows_without_header(self):
        ws = Mock()
        RowModelService().append(ws, [Person("Ana", 30), Person("Bob", 25)], "USER_ENTERED")
        ws.append_rows.assert_called_once_with([["Ana", 30], ["Bob", 25]], "USER_ENTERED")

    def test_append_empty_is_noop(self):
        ws = Mock()
        assert RowModelService().append(ws, [], "RAW") is None
        ws.append_rows.assert_not_called()


class TestWrite:
    def test_write_includes_header_and_clears(self):
        ws = Mock()
        RowModelService().write(ws, [Person("Ana", 30)], True, True, "RAW")
        ws.clear.assert_called_once_with()
        ws.update.assert_called_once_with([["nombre", "edad"], ["Ana", 30]], "RAW")

    def test_write_without_header_or_clear(self):
        ws = Mock()
        RowModelService().write(ws, [Person("Ana", 30)], False, False, "RAW")
        ws.clear.assert_not_called()
        ws.update.assert_called_once_with([["Ana", 30]], "RAW")
