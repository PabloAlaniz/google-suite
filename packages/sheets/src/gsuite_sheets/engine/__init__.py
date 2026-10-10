"""Sheets engine incorporated from GSpreadManager 3.0 (history: tag archive/gspreadmanager).

Internal to gsuite_sheets: domain value objects, ports, application services,
the in-memory backend and the SheetManager/WorksheetContext orchestration.
The public API is gsuite_sheets.Sheets / Spreadsheet / Worksheet; requests
go through gsuite_sheets.engine_adapter, which implements the ports on top
of google-suite's client (retries, errors and auth from gsuite_core).
"""

import logging

from .async_facade import AsyncSheetManager, AsyncWorksheetContext
from .config import DEFAULT_VALUE_INPUT_OPTION
from .domain.errors import (
    ApiError,
    CellNotFoundError,
    GSpreadManagerError,
    InsertError,
    PermissionDeniedError,
    QuotaExceededError,
    SchemaError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from .domain.export import ExportFormat
from .domain.values import Border, Borders, CellFormat, Color, NumberFormat, TextFormat
from .facade import SheetManager, WorksheetContext

# Logging opt-in: la librería no configura handlers; el usuario activa
# ``logging.getLogger("gsuite_sheets.engine")`` si quiere ver requests/retries/caché.
logging.getLogger(__name__).addHandler(logging.NullHandler())


__all__ = [
    "AsyncSheetManager",
    "AsyncWorksheetContext",
    "DEFAULT_VALUE_INPUT_OPTION",
    "ApiError",
    "Border",
    "Borders",
    "CellFormat",
    "CellNotFoundError",
    "Color",
    "ExportFormat",
    "GSpreadManagerError",
    "InsertError",
    "NumberFormat",
    "PermissionDeniedError",
    "QuotaExceededError",
    "SchemaError",
    "SheetManager",
    "SpreadsheetNotFoundError",
    "TextFormat",
    "WorksheetContext",
    "WorksheetNotFoundError",
]
