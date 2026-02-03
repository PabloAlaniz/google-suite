"""Spreadsheet entity."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

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
        self.worksheets.append(ws)
        return ws

    def del_worksheet(self, worksheet: Worksheet) -> bool:
        """Delete a worksheet."""
        if not self._sheets:
            raise RuntimeError("Spreadsheet not linked to Sheets client")

        success = self._sheets.delete_worksheet(self.id, worksheet.id)
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
