"""Tests unitarios de los value objects del dominio (``gspreadmanager.domain.values``).

Cubren: inmutabilidad (frozen), serialización a la forma JSON de la Sheets API y
equivalencia con los dicts que el conector arma inline para validación y formato
condicional.
"""

import dataclasses

import pytest
from gspread.utils import a1_range_to_grid_range
from gspreadmanager.domain.errors import (
    GSpreadManagerError,
    InvalidColorError,
    InvalidIdentifierError,
    InvalidRangeError,
)
from gspreadmanager.domain.values import (
    A1Range,
    Border,
    Borders,
    CellFormat,
    Color,
    Condition,
    ConditionalFormatRule,
    DataValidationRule,
    GridRange,
    NumberFormat,
    SpreadsheetId,
    TextFormat,
    WorksheetRef,
)


class TestFrozen:
    def test_color_is_frozen(self):
        color = Color(red=1.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            color.red = 0.5  # type: ignore[misc]

    def test_cell_format_is_frozen(self):
        fmt = CellFormat()
        with pytest.raises(dataclasses.FrozenInstanceError):
            fmt.wrap_strategy = "WRAP"  # type: ignore[misc]

    def test_value_objects_are_hashable(self):
        # frozen + campos hashables => usables en sets/dicts
        assert len({Color(red=1.0), Color(red=1.0)}) == 1
        assert len({NumberFormat("NUMBER"), NumberFormat("NUMBER")}) == 1


class TestColor:
    def test_to_dict(self):
        assert Color(0.1, 0.2, 0.3, 0.4).to_dict() == {
            "red": 0.1,
            "green": 0.2,
            "blue": 0.3,
            "alpha": 0.4,
        }

    def test_from_hex(self):
        c = Color.from_hex("#FF8000")
        assert c.red == 1.0
        assert c.green == pytest.approx(128 / 255)
        assert c.blue == 0.0

    def test_from_hex_without_prefix(self):
        assert Color.from_hex("FF8000") == Color.from_hex("#FF8000")

    def test_from_hex_invalid_raises_value_error(self):
        # InvalidColorError subclasea ValueError: compatibilidad hacia atrás.
        with pytest.raises(ValueError, match="hex inválido"):
            Color.from_hex("#FFF")

    def test_from_hex_invalid_raises_domain_error(self):
        with pytest.raises(InvalidColorError):
            Color.from_hex("#FFF")
        assert issubclass(InvalidColorError, GSpreadManagerError)


class TestFormatSerialization:
    def test_text_format_omits_none(self):
        assert TextFormat(bold=True).to_dict() == {"bold": True}

    def test_text_format_camel_case_and_nested_color(self):
        out = TextFormat(font_size=12, foreground_color=Color(red=1.0)).to_dict()
        assert out == {
            "fontSize": 12,
            "foregroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0, "alpha": 1.0},
        }

    def test_number_format(self):
        assert NumberFormat("PERCENT", "0.00%").to_dict() == {"type": "PERCENT", "pattern": "0.00%"}

    def test_border_and_borders(self):
        borders = Borders(top=Border(style="SOLID", color=Color(blue=1.0)))
        assert borders.to_dict() == {
            "top": {
                "style": "SOLID",
                "color": {"red": 0.0, "green": 0.0, "blue": 1.0, "alpha": 1.0},
            }
        }

    def test_cell_format_full(self):
        fmt = CellFormat(
            background_color=Color(red=1.0),
            text_format=TextFormat(bold=True),
            horizontal_alignment="CENTER",
        )
        assert fmt.to_dict() == {
            "backgroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0, "alpha": 1.0},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        }


class TestRanges:
    @pytest.mark.parametrize("value", ["A1", "A1:C10", "A:A", "1:1", "AA10:AB20"])
    def test_a1_range_valid(self, value):
        assert str(A1Range(value)) == value

    @pytest.mark.parametrize("value", ["", "!!", "A1:", "Hoja1!A1"])
    def test_a1_range_invalid(self, value):
        with pytest.raises(InvalidRangeError):
            A1Range(value)

    def test_a1_range_with_sheet(self):
        assert A1Range("A1:C10").with_sheet("Hoja1") == "Hoja1!A1:C10"

    def test_grid_range_round_trip_with_gspread(self):
        # El conector usa a1_range_to_grid_range; GridRange debe reproducir su dict.
        grid = a1_range_to_grid_range("A1:B5", 0)
        assert GridRange.from_dict(grid).to_dict() == grid

    def test_grid_range_omits_absent_bounds(self):
        assert GridRange(sheet_id=7).to_dict() == {"sheetId": 7}

    def test_spreadsheet_id_validates(self):
        assert str(SpreadsheetId("abc123")) == "abc123"
        with pytest.raises(InvalidIdentifierError):
            SpreadsheetId("   ")

    def test_worksheet_ref(self):
        ref = WorksheetRef("MiDoc", "Hoja1")
        assert ref.doc_name == "MiDoc"
        assert ref.tab_name == "Hoja1"
        with pytest.raises(InvalidIdentifierError):
            WorksheetRef("")


class TestCondition:
    def test_without_values(self):
        assert Condition.of("BOOLEAN").to_dict() == {"type": "BOOLEAN"}

    def test_with_values_normalizes_sequence(self):
        cond = Condition.of("ONE_OF_LIST", ["A", "B"])
        assert cond.values == ("A", "B")
        assert cond.to_dict() == {
            "type": "ONE_OF_LIST",
            "values": [{"userEnteredValue": "A"}, {"userEnteredValue": "B"}],
        }

    def test_values_coerced_to_str(self):
        assert Condition.of("NUMBER_BETWEEN", [1, 10]).to_dict()["values"] == [
            {"userEnteredValue": "1"},
            {"userEnteredValue": "10"},
        ]


class TestRequestEquivalence:
    """Los VOs deben reproducir exactamente los dicts que arma el conector inline."""

    def test_data_validation_request(self):
        grid = a1_range_to_grid_range("A1:A10", 0)
        rule = DataValidationRule(
            Condition.of("ONE_OF_LIST", ["Sí", "No"]), strict=True, show_custom_ui=True
        )
        # Forma esperada según gspreadmanager/connector.py:set_data_validation
        expected = {
            "setDataValidation": {
                "range": grid,
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
        assert rule.to_request(GridRange.from_dict(grid)) == expected

    def test_data_validation_request_without_values(self):
        grid = a1_range_to_grid_range("A1:A10", 0)
        rule = DataValidationRule(Condition.of("BOOLEAN"))
        expected = {
            "setDataValidation": {
                "range": grid,
                "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
            }
        }
        assert rule.to_request(GridRange.from_dict(grid)) == expected

    def test_conditional_format_request(self):
        grid = a1_range_to_grid_range("B2:B100", 0)
        cell_format = CellFormat(background_color=Color.from_hex("#F4CCCC"))
        rule = ConditionalFormatRule(Condition.of("NUMBER_LESS", [0]), cell_format, index=0)
        # Réplica de gspreadmanager/connector.py:add_conditional_format
        expected = {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [grid],
                    "booleanRule": {
                        "condition": {
                            "type": "NUMBER_LESS",
                            "values": [{"userEnteredValue": "0"}],
                        },
                        "format": cell_format.to_dict(),
                    },
                },
                "index": 0,
            }
        }
        assert rule.to_request(GridRange.from_dict(grid)) == expected
