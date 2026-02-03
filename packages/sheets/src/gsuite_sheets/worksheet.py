"""Worksheet entity."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from gsuite_sheets.spreadsheet import Spreadsheet


@dataclass
class Worksheet:
    """
    A worksheet (tab) within a spreadsheet.

    Provides methods for reading and writing cell data.
    """

    id: int
    title: str
    index: int
    row_count: int = 1000
    column_count: int = 26

    _spreadsheet: Optional["Spreadsheet"] = field(default=None, repr=False)

    @property
    def url(self) -> str | None:
        """Get URL to this specific worksheet."""
        if self._spreadsheet:
            return f"{self._spreadsheet.url}#gid={self.id}"
        return None

    # ========== Reading ==========

    def get(self, range: str = "A1") -> list[list[Any]]:
        """
        Get values from a range.

        Args:
            range: A1 notation (e.g., "A1:B10", "A:C", "1:5")

        Returns:
            2D list of values
        """
        if not self._spreadsheet:
            raise RuntimeError("Worksheet not linked to spreadsheet")
        return self._spreadsheet._sheets.get_values(self._spreadsheet.id, f"{self.title}!{range}")

    def get_all_values(self) -> list[list[Any]]:
        """Get all values in the worksheet."""
        return self.get("A1:ZZ")

    def get_all_records(self, head: int = 1) -> list[dict]:
        """
        Get all rows as list of dicts using row as headers.

        Args:
            head: Row number to use as headers (1-indexed)

        Returns:
            List of dicts with header keys
        """
        values = self.get_all_values()
        if len(values) < head:
            return []

        headers = values[head - 1]
        records = []

        for row in values[head:]:
            # Pad row to match headers length
            padded = row + [""] * (len(headers) - len(row))
            record = dict(zip(headers, padded))
            records.append(record)

        return records

    def row_values(self, row: int) -> list[Any]:
        """Get all values in a row (1-indexed)."""
        values = self.get(f"{row}:{row}")
        return values[0] if values else []

    def col_values(self, col: int) -> list[Any]:
        """Get all values in a column (1-indexed)."""
        col_letter = self._col_to_letter(col)
        values = self.get(f"{col_letter}:{col_letter}")
        return [row[0] if row else "" for row in values]

    def cell(self, row: int, col: int) -> Any:
        """Get a single cell value (1-indexed)."""
        col_letter = self._col_to_letter(col)
        values = self.get(f"{col_letter}{row}")
        if values and values[0]:
            return values[0][0]
        return ""

    # ========== Writing ==========

    def update(self, range: str, values: list[list[Any]]) -> dict:
        """
        Update a range with values.

        Args:
            range: A1 notation
            values: 2D list of values

        Returns:
            Update response
        """
        if not self._spreadsheet:
            raise RuntimeError("Worksheet not linked to spreadsheet")
        return self._spreadsheet._sheets.update_values(
            self._spreadsheet.id, f"{self.title}!{range}", values
        )

    def update_cell(self, row: int, col: int, value: Any) -> dict:
        """Update a single cell (1-indexed)."""
        col_letter = self._col_to_letter(col)
        return self.update(f"{col_letter}{row}", [[value]])

    def append_row(self, values: list[Any]) -> dict:
        """Append a row to the end of the worksheet."""
        if not self._spreadsheet:
            raise RuntimeError("Worksheet not linked to spreadsheet")
        return self._spreadsheet._sheets.append_values(
            self._spreadsheet.id, f"{self.title}!A1", [values]
        )

    def append_rows(self, rows: list[list[Any]]) -> dict:
        """Append multiple rows."""
        if not self._spreadsheet:
            raise RuntimeError("Worksheet not linked to spreadsheet")
        return self._spreadsheet._sheets.append_values(
            self._spreadsheet.id, f"{self.title}!A1", rows
        )

    def clear(self, range: str | None = None) -> dict:
        """
        Clear values from a range or entire worksheet.

        Args:
            range: A1 notation (default: entire sheet)
        """
        if not self._spreadsheet:
            raise RuntimeError("Worksheet not linked to spreadsheet")

        full_range = f"{self.title}!{range}" if range else self.title
        return self._spreadsheet._sheets.clear_values(self._spreadsheet.id, full_range)

    # ========== Search ==========

    def find(self, query: str) -> tuple[int, int] | None:
        """
        Find first cell containing query.

        Returns:
            (row, col) tuple or None
        """
        values = self.get_all_values()
        for row_idx, row in enumerate(values):
            for col_idx, cell in enumerate(row):
                if str(cell) == query:
                    return (row_idx + 1, col_idx + 1)
        return None

    def findall(self, query: str) -> list[tuple[int, int]]:
        """Find all cells containing query."""
        values = self.get_all_values()
        results = []
        for row_idx, row in enumerate(values):
            for col_idx, cell in enumerate(row):
                if str(cell) == query:
                    results.append((row_idx + 1, col_idx + 1))
        return results

    # ========== Helpers ==========

    @staticmethod
    def _col_to_letter(col: int) -> str:
        """Convert column number to letter (1=A, 27=AA)."""
        result = ""
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            result = chr(65 + remainder) + result
        return result
