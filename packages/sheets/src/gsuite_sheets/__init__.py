"""Google Suite Sheets - Google Sheets client.

Sheets / Spreadsheet / Worksheet are the API. The features beyond reading and
writing values (validation, conditional formats, charts, typed rows, upsert,
streaming, ...) run on the engine incorporated from GSpreadManager.
"""

__version__ = "0.1.0"

from gsuite_sheets.aio import AsyncSheets, AsyncSpreadsheet, AsyncWorksheet
from gsuite_sheets.client import Sheets
from gsuite_sheets.engine.domain.errors import (
    CellNotFoundError,
    InvalidColorError,
    InvalidRangeError,
    SchemaError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from gsuite_sheets.engine.domain.export import ExportFormat
from gsuite_sheets.engine.domain.values import (
    Border,
    Borders,
    CellFormat,
    Color,
    NumberFormat,
    TextFormat,
)
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet

__all__ = [
    "AsyncSheets",
    "AsyncSpreadsheet",
    "AsyncWorksheet",
    "Border",
    "Borders",
    "CellFormat",
    "CellNotFoundError",
    "Color",
    "ExportFormat",
    "InvalidColorError",
    "InvalidRangeError",
    "NumberFormat",
    "SchemaError",
    "Sheets",
    "Spreadsheet",
    "SpreadsheetNotFoundError",
    "TextFormat",
    "Worksheet",
    "WorksheetNotFoundError",
]
