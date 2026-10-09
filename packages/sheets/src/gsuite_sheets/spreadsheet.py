"""Spreadsheet entity."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from gsuite_sheets.client import Sheets

from gsuite_sheets.worksheet import Worksheet


@dataclass
class Spreadsheet:
    """
    A Google Spreadsheet.

    Contains multiple worksheets (tabs).
    """

    id: str
    title: str
    url: str
    locale: str = "en_US"
    time_zone: str = "America/New_York"
    worksheets: list[Worksheet] = field(default_factory=list)

    _sheets: Optional["Sheets"] = field(default=None, repr=False)

    @property
    def sheet1(self) -> Worksheet | None:
        """Get the first worksheet (convenience property like gspread)."""
        return self.worksheets[0] if self.worksheets else None

    def worksheet(self, title: str) -> Worksheet | None:
        """Get worksheet by title."""
        for ws in self.worksheets:
            if ws.title == title:
                return ws
        return None

    def get_worksheet(self, index: int) -> Worksheet | None:
        """Get worksheet by index (0-indexed)."""
        if 0 <= index < len(self.worksheets):
            return self.worksheets[index]
        return None

    def add_worksheet(
        self,
        title: str,
        rows: int = 1000,
        cols: int = 26,
    ) -> Worksheet:
        """
        Add a new worksheet.

        Args:
            title: Worksheet title
            rows: Number of rows
            cols: Number of columns

        Returns:
            Created Worksheet
        """
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")

        ws = self._sheets.add_worksheet(self.id, title, rows, cols)
        self._sheets._forget(self.id)
        # Without the link, ws.update() & co. raised "not linked to spreadsheet"
        ws._spreadsheet = self
        self.worksheets.append(ws)
        return ws

    def duplicate_worksheet(self, worksheet: Worksheet, new_title: str | None = None) -> Worksheet:
        """Copy a worksheet (default name: "Copy of ...")."""
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")

        ws = self._sheets.duplicate_worksheet(self.id, worksheet.id, new_title)
        self._sheets._forget(self.id)
        ws._spreadsheet = self
        self.worksheets.append(ws)
        return ws

    def del_worksheet(self, worksheet: Worksheet) -> bool:
        """Delete a worksheet."""
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")

        success = self._sheets.delete_worksheet(self.id, worksheet.id)
        self._sheets._forget(self.id)
        if success:
            self.worksheets = [ws for ws in self.worksheets if ws.id != worksheet.id]
        return success

    def share(
        self,
        email: str,
        role: str = "reader",
        notify: bool = True,
    ) -> bool:
        """
        Share spreadsheet with someone.

        Args:
            email: Email to share with
            role: Permission role (reader, writer)
            notify: Send notification email
        """
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")
        return self._sheets.share(self.id, email, role, notify)

    # ========== Document-level features (engine) ==========

    def _manager(self) -> Any:
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")
        return self._sheets._engine_manager(self.id)

    def worksheet_or_create(self, title: str, rows: int = 100, cols: int = 26) -> Worksheet:
        """The tab titled ``title``, created if missing."""
        existing = self.worksheet(title)
        return existing if existing else self.add_worksheet(title, rows, cols)

    def worksheet_by_id(self, sheet_id: int) -> Worksheet | None:
        """Tab by its numeric ID (gid)."""
        return next((ws for ws in self.worksheets if ws.id == sheet_id), None)

    def update_title(self, title: str) -> None:
        """Rename the spreadsheet."""
        self._manager().update_title(title)
        self.title = title

    def update_locale(self, locale: str) -> None:
        """Locale used for formats and functions, e.g. "es_AR"."""
        self._manager().update_locale(locale)
        self.locale = locale

    def update_timezone(self, timezone: str) -> None:
        """Time zone, e.g. "America/Argentina/Buenos_Aires"."""
        self._manager().update_timezone(timezone)
        self.time_zone = timezone

    def export(self, format: str = "pdf") -> bytes:
        """
        The whole spreadsheet as bytes.

        Args:
            format: "pdf", "xlsx", "ods", "csv", "tsv" (first sheet only) or "html" (zip)
        """
        from gsuite_sheets.engine.domain.export import ExportFormat

        formats = {
            "pdf": ExportFormat.PDF,
            "xlsx": ExportFormat.EXCEL,
            "ods": ExportFormat.ODS,
            "csv": ExportFormat.CSV,
            "tsv": ExportFormat.TSV,
            "html": ExportFormat.HTML,
        }
        content: bytes = self._manager().export(formats.get(format.lower(), format))
        return content

    def list_named_ranges(self) -> list[dict[str, Any]]:
        """Named ranges (define them with Worksheet.define_named_range)."""
        return list(self._manager().list_named_ranges())

    def delete_named_range(self, named_range_id: str) -> None:
        """Remove a named range."""
        self._manager().delete_named_range(named_range_id)

    def set_developer_metadata(self, key: str, value: str, visibility: str = "DOCUMENT") -> None:
        """Attach a hidden key/value to the spreadsheet."""
        self._manager().set_developer_metadata(key, value, visibility)

    def list_developer_metadata(self) -> list[dict[str, Any]]:
        """Developer metadata of the spreadsheet and its tabs."""
        return list(self._manager().list_developer_metadata())

    def delete_developer_metadata(self, key: str) -> None:
        """Remove developer metadata by key."""
        self._manager().delete_developer_metadata(key)

    def list_permissions(self) -> list[dict[str, Any]]:
        """Who has access."""
        return list(self._manager().list_permissions())

    def remove_permission(self, value: str, role: str = "any") -> list[str]:
        """Revoke access of an email or domain (optionally only for ``role``); returns removed IDs."""
        return list(self._manager().remove_permission(value, role))
