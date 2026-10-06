"""Tests aislados de ``ValidationService`` con hoja falsa (sin gspread real)."""

from typing import Any
from unittest.mock import Mock

import pytest
from gspreadmanager.application.validation_service import ValidationService
from gspreadmanager.domain.values import CellFormat, Color, GridRange


@pytest.fixture
def service():
    return ValidationService()


def _request(worksheet: Any) -> Any:
    """Devuelve el dict pasado a batch_update."""
    return worksheet.spreadsheet.batch_update.call_args[0][0]


def test_set_data_validation_builds_request(service):
    ws = Mock()
    grid = GridRange(sheet_id=0, start_row_index=0, end_row_index=10)
    service.set_data_validation(
        ws, grid, "ONE_OF_LIST", ["Sí", "No"], strict=True, show_custom_ui=True
    )
    assert _request(ws) == {
        "requests": [
            {
                "setDataValidation": {
                    "range": grid.to_dict(),
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": "Sí"}, {"userEnteredValue": "No"}],
                        },
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            }
        ]
    }


def test_set_data_validation_boolean_without_values(service):
    ws = Mock()
    grid = GridRange(sheet_id=0)
    service.set_data_validation(ws, grid, "BOOLEAN", None, strict=True, show_custom_ui=True)
    condition = _request(ws)["requests"][0]["setDataValidation"]["rule"]["condition"]
    assert condition == {"type": "BOOLEAN"}


def test_add_conditional_format_builds_request(service):
    ws = Mock()
    grid = GridRange(sheet_id=5)
    fmt = CellFormat(background_color=Color.from_hex("#F4CCCC"))
    service.add_conditional_format(ws, grid, "NUMBER_LESS", [0], fmt, index=0)
    assert _request(ws) == {
        "requests": [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [grid.to_dict()],
                        "booleanRule": {
                            "condition": {
                                "type": "NUMBER_LESS",
                                "values": [{"userEnteredValue": "0"}],
                            },
                            "format": fmt.to_dict(),
                        },
                    },
                    "index": 0,
                }
            }
        ]
    }
