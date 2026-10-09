"""Worksheet entity."""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from gsuite_sheets.a1 import a1, column_letter

if TYPE_CHECKING:
    import pandas as pd

    from gsuite_sheets.client import Sheets, ValueInput, ValueRender
    from gsuite_sheets.spreadsheet import Spreadsheet


@dataclass
class Worksheet:
    """
    A worksheet (tab) within a spreadsheet.

    Provides methods for reading and writing cell data. Ranges are A1
    notation without the sheet title ("A1:C10"); the title is added and
    quoted for you, so tabs named "2024" or "Pablo's" work.
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

    def _client(self) -> tuple["Sheets", str]:
        if not self._spreadsheet or not self._spreadsheet._sheets:
            raise RuntimeError("Worksheet not linked to spreadsheet")
        return self._spreadsheet._sheets, self._spreadsheet.id

    def _range(self, cell_range: str | None = None) -> str:
        return a1(self.title, cell_range)

    # ========== Reading ==========

    def get(
        self, range: str = "A1", value_render: "ValueRender" = "FORMATTED_VALUE"
    ) -> list[list[Any]]:
        """
        Get values from a range.

        Args:
            range: A1 notation (e.g., "A1:B10", "A:C", "1:5")
            value_render: FORMATTED_VALUE, UNFORMATTED_VALUE or FORMULA

        Returns:
            2D list of values
        """
        sheets, spreadsheet_id = self._client()
        return sheets.get_values(spreadsheet_id, self._range(range), value_render)

    def batch_get(self, ranges: list[str]) -> list[list[list[Any]]]:
        """Get several ranges in one request, in the order given."""
        sheets, spreadsheet_id = self._client()
        return sheets.batch_get_values(spreadsheet_id, [self._range(r) for r in ranges])

    def get_all_values(self) -> list[list[Any]]:
        """Get all values in the worksheet."""
        sheets, spreadsheet_id = self._client()
        # The bare title is the whole sheet; "A1:ZZ" (as this used to do)
        # silently dropped columns after ZZ.
        return sheets.get_values(spreadsheet_id, self._range())

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

    def update(
        self, range: str, values: list[list[Any]], value_input: "ValueInput" = "USER_ENTERED"
    ) -> dict:
        """
        Update a range with values.

        Args:
            range: A1 notation (a single cell writes from there down/right)
            values: 2D list of values
            value_input: USER_ENTERED (parse like the UI: formulas, dates) or
                RAW (store as-is; use for untrusted text)

        Returns:
            Update response
        """
        sheets, spreadsheet_id = self._client()
        return sheets.update_values(spreadsheet_id, self._range(range), values, value_input)

    def update_cell(self, row: int, col: int, value: Any) -> dict:
        """Update a single cell (1-indexed)."""
        col_letter = self._col_to_letter(col)
        return self.update(f"{col_letter}{row}", [[value]])

    def append_row(self, values: list[Any], value_input: "ValueInput" = "USER_ENTERED") -> dict:
        """Append a row to the end of the worksheet."""
        return self.append_rows([values], value_input)

    def append_rows(
        self, rows: list[list[Any]], value_input: "ValueInput" = "USER_ENTERED"
    ) -> dict:
        """Append multiple rows."""
        sheets, spreadsheet_id = self._client()
        return sheets.append_values(spreadsheet_id, self._range("A1"), rows, value_input)

    def clear(self, range: str | None = None) -> dict:
        """
        Clear values from a range or entire worksheet.

        Args:
            range: A1 notation (default: entire sheet)
        """
        sheets, spreadsheet_id = self._client()
        return sheets.clear_values(spreadsheet_id, self._range(range))

    # ========== Formatting and structure ==========

    def format(self, range: str, cell_format: dict) -> None:
        """
        Format a range.

        Example:
            ws.format("A1:Z1", {"textFormat": {"bold": True}})
            ws.format("B2:B100", {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
        """
        sheets, spreadsheet_id = self._client()
        sheets.format_range(spreadsheet_id, self.id, range, cell_format)

    def freeze(self, rows: int | None = None, cols: int | None = None) -> None:
        """Freeze header rows and/or columns (0 unfreezes)."""
        sheets, spreadsheet_id = self._client()
        sheets.freeze(spreadsheet_id, self.id, rows, cols)

    def protect(
        self,
        range: str | None = None,
        description: str | None = None,
        editors: list[str] | None = None,
        warning_only: bool = False,
    ) -> int:
        """Protect a range, or the whole sheet. Returns the protected range ID."""
        sheets, spreadsheet_id = self._client()
        return sheets.protect_range(
            spreadsheet_id, self.id, range, description, editors, warning_only
        )

    def rename(self, title: str) -> None:
        """Rename this worksheet."""
        sheets, spreadsheet_id = self._client()
        sheets.rename_worksheet(spreadsheet_id, self.id, title)
        self.title = title

    def replace(
        self,
        find: str,
        replacement: str,
        match_case: bool = False,
        match_entire_cell: bool = False,
        regex: bool = False,
    ) -> int:
        """
        Find and replace in this worksheet (server-side).

        Returns:
            Number of occurrences changed
        """
        sheets, spreadsheet_id = self._client()
        return sheets.find_replace(
            spreadsheet_id,
            find,
            replacement,
            sheet_id=self.id,
            match_case=match_case,
            match_entire_cell=match_entire_cell,
            regex=regex,
        )

    # ========== Search ==========

    @staticmethod
    def _matches(cell: Any, query: "str | re.Pattern[str]") -> bool:
        if isinstance(query, re.Pattern):
            return query.search(str(cell)) is not None
        return str(cell) == query

    def find(self, query: "str | re.Pattern[str]") -> tuple[int, int] | None:
        """
        Find the first cell equal to `query`, or matching it if it's a regex.

        Example:
            ws.find("Total")
            ws.find(re.compile(r"\\d{3}-\\d{4}"))

        Returns:
            (row, col) tuple (1-indexed) or None
        """
        for row_idx, row in enumerate(self.get_all_values()):
            for col_idx, cell in enumerate(row):
                if self._matches(cell, query):
                    return (row_idx + 1, col_idx + 1)
        return None

    def findall(self, query: "str | re.Pattern[str]") -> list[tuple[int, int]]:
        """Find all cells equal to `query`, or matching it if it's a regex."""
        return [
            (row_idx + 1, col_idx + 1)
            for row_idx, row in enumerate(self.get_all_values())
            for col_idx, cell in enumerate(row)
            if self._matches(cell, query)
        ]

    # ========== pandas ==========

    def to_dataframe(self, header_row: int = 1) -> "pd.DataFrame":
        """
        Read the worksheet into a pandas DataFrame (needs gsuite-sdk[pandas]).

        Args:
            header_row: Row with column names (1-indexed); rows above it are skipped

        Values come back as displayed text; convert types in pandas as needed.
        """
        pd = _pandas()
        values = self.get_all_values()
        if len(values) < header_row:
            return pd.DataFrame()

        headers = values[header_row - 1]
        rows = values[header_row:]
        width = max([len(headers), *(len(r) for r in rows)])
        headers = headers + [f"column_{i + 1}" for i in range(len(headers), width)]
        return pd.DataFrame([r + [""] * (width - len(r)) for r in rows], columns=headers)

    def from_dataframe(
        self,
        df: "pd.DataFrame",
        start: str = "A1",
        include_header: bool = True,
        include_index: bool = False,
        clear: bool = False,
        value_input: "ValueInput" = "USER_ENTERED",
    ) -> dict:
        """
        Write a pandas DataFrame starting at `start`.

        NaN/None become empty cells and dates are written as ISO strings.

        Args:
            clear: Clear the worksheet first (otherwise old cells outside the
                new data remain)
        """
        _pandas()
        frame = df.reset_index() if include_index else df
        # NaN, NaT and pd.NA all become None, then empty cells
        frame = frame.astype(object).where(frame.notna(), None)

        rows: list[list[Any]] = []
        if include_header:
            rows.append([str(c) for c in frame.columns])
        rows.extend([_cell_value(v) for v in record] for record in frame.itertuples(index=False))

        if clear:
            self.clear()
        return self.update(start, rows, value_input)

    # ========== Helpers ==========

    @staticmethod
    def _col_to_letter(col: int) -> str:
        """Convert column number to letter (1=A, 27=AA)."""
        return column_letter(col - 1)


def _pandas() -> Any:
    try:
        import pandas
    except ImportError as e:
        raise ImportError("DataFrame support needs pandas: pip install 'gsuite-sdk[pandas]'") from e
    return pandas


def _cell_value(value: Any) -> Any:
    """A DataFrame value as something the Sheets API accepts in JSON."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # pandas Timestamp, numpy datetime64 wrappers
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars aren't JSON serializable
        return value.item()
    return value
