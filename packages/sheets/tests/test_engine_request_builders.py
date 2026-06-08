"""Golden-tests de ``infrastructure.request_builders``.

Verifican la conversión real A1 -> GridRange (vía gspread) y que las peticiones armadas
desde los value objects tengan exactamente la forma que espera ``spreadsheets.batchUpdate``.
"""

from gspread.utils import a1_range_to_grid_range
from gspreadmanager.domain.values import (
    CellFormat,
    Color,
    Condition,
    ConditionalFormatRule,
    DataValidationRule,
)
from gspreadmanager.infrastructure.request_builders import (
    conditional_format_request,
    data_validation_request,
    grid_range,
)


def test_grid_range_matches_gspread_conversion():
    assert grid_range("A1:B5", 7).to_dict() == a1_range_to_grid_range("A1:B5", 7)


def test_data_validation_request_golden():
    rule = DataValidationRule(Condition.of("ONE_OF_LIST", ["Sí", "No"]))
    request = data_validation_request(rule, "A1:A10", 12345)
    assert request == {
        "setDataValidation": {
            "range": a1_range_to_grid_range("A1:A10", 12345),
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


def test_data_validation_request_boolean_without_values():
    rule = DataValidationRule(Condition.of("BOOLEAN"))
    request = data_validation_request(rule, "D2:D10", 0)
    assert request["setDataValidation"]["rule"]["condition"] == {"type": "BOOLEAN"}


def test_conditional_format_request_golden():
    fmt = CellFormat(background_color=Color.from_hex("#F4CCCC"))
    rule = ConditionalFormatRule(Condition.of("NUMBER_LESS", [0]), fmt, index=0)
    request = conditional_format_request(rule, "B2:B100", 99)
    assert request == {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [a1_range_to_grid_range("B2:B100", 99)],
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
