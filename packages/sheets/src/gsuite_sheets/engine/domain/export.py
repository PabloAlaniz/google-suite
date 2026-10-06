"""Formatos de exportación (mime types) para ``SheetManager.export``."""

from __future__ import annotations

from enum import Enum


class ExportFormat(str, Enum):
    """Mime types soportados por la exportación de Google Sheets."""

    PDF = "application/pdf"
    CSV = "text/csv"
    TSV = "text/tab-separated-values"
    EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ODS = "application/x-vnd.oasis.opendocument.spreadsheet"
    HTML = "application/zip"
