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
from .visualization import (
    BandingSpec,
    ChartSpec,
    DeveloperMetadataEntry,
    PivotField,
    PivotTableSpec,
    PivotValue,
)

__all__ = [
    "A1Range",
    "BandingSpec",
    "Border",
    "Borders",
    "CellFormat",
    "ChartSpec",
    "Color",
    "Condition",
    "ConditionalFormatRule",
    "DataValidationRule",
    "DeveloperMetadataEntry",
    "GridRange",
    "NumberFormat",
    "PivotField",
    "PivotTableSpec",
    "PivotValue",
    "SpreadsheetId",
    "TextFormat",
    "WorksheetRef",
    "column_to_letter",
    "letter_to_column",
    "rowcol_to_a1",
]
