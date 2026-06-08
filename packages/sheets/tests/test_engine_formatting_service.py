"""Tests aislados de ``FormattingService`` con hoja falsa (sin gspread real)."""

from unittest.mock import Mock

import pytest
from gspreadmanager.application.formatting_service import FormattingService
from gspreadmanager.domain.values import CellFormat, Color


@pytest.fixture
def service():
    return FormattingService()


def test_apply_serializes_cell_format(service):
    ws = Mock()
    fmt = CellFormat(background_color=Color(red=1.0))
    service.apply(ws, "A1:B2", fmt)
    ws.format.assert_called_once_with("A1:B2", fmt.to_dict())


def test_freeze(service):
    ws = Mock()
    service.freeze(ws, 1, 2)
    ws.freeze.assert_called_once_with(1, 2)


def test_merge(service):
    ws = Mock()
    service.merge(ws, "A1:B2", "MERGE_ALL")
    ws.merge_cells.assert_called_once_with("A1:B2", "MERGE_ALL")


def test_header_format_with_background():
    fmt = FormattingService().header_format("#FFFFFF")
    assert fmt.text_format is not None
    assert fmt.text_format.bold is True
    assert fmt.background_color == Color.from_hex("#FFFFFF")


def test_header_format_without_background():
    fmt = FormattingService().header_format(None)
    assert fmt.background_color is None
    assert fmt.text_format is not None
    assert fmt.text_format.bold is True


def test_text_format():
    fmt = FormattingService().text_format(bold=True, font_size=12, color=Color(blue=1.0))
    assert fmt.text_format is not None
    assert fmt.text_format.bold is True
    assert fmt.text_format.font_size == 12
    assert fmt.text_format.foreground_color == Color(blue=1.0)


def test_number_format():
    fmt = FormattingService().number_format("0.00%", "PERCENT")
    assert fmt.number_format is not None
    assert fmt.number_format.type == "PERCENT"
    assert fmt.number_format.pattern == "0.00%"
