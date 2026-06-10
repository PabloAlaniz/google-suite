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
# ``logging.getLogger("gspreadmanager")`` si quiere ver requests/retries/caché.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "3.0.0"

__all__ = [
    "DEFAULT_VALUE_INPUT_OPTION",
    "ApiError",
    "AsyncSheetManager",
    "AsyncWorksheetContext",
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
    "__version__",
]
