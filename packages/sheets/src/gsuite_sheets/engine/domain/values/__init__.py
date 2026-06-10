"""Value objects del dominio (formato, rangos, reglas de validación)."""

from __future__ import annotations

from .border import Border, Borders
from .cell_format import CellFormat
from .color import Color
from .number_format import NumberFormat
from .ranges import (
    A1Range,
    GridRange,
    SpreadsheetId,
    WorksheetRef,
    column_to_letter,
    letter_to_column,
    rowcol_to_a1,
)
from .text_format import TextFormat
from .validation import Condition, ConditionalFormatRule, DataValidationRule

__all__ = [
    "A1Range",
    "Border",
    "Borders",
    "CellFormat",
    "Color",
    "Condition",
    "ConditionalFormatRule",
    "DataValidationRule",
    "GridRange",
    "NumberFormat",
    "SpreadsheetId",
    "TextFormat",
    "WorksheetRef",
    "column_to_letter",
    "letter_to_column",
    "rowcol_to_a1",
]
