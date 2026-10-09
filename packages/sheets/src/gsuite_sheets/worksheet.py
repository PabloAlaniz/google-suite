"""Worksheet entity."""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from gsuite_sheets.a1 import a1, column_letter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import pandas as pd

    from gsuite_sheets.client import Sheets, ValueInput, ValueRender
    from gsuite_sheets.engine.domain.values import CellFormat, Color
    from gsuite_sheets.spreadsheet import Spreadsheet

    Where = dict[str, Any] | Callable[[dict[str, str]], bool]


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

    @property
    def _ctx(self) -> Any:
        """The engine's WorksheetContext for this tab (features below delegate to it)."""
        sheets, spreadsheet_id = self._client()
        return sheets._engine_worksheet(spreadsheet_id, self.title)

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

    def batch_update(
        self, data: list[dict[str, Any]], value_input: "ValueInput" = "USER_ENTERED"
    ) -> dict:
        """Write several ranges of this sheet in one request: [{"range": "A1:B2", "values": [...]}]."""
        sheets, spreadsheet_id = self._client()
        qualified = [{"range": self._range(d["range"]), "values": d["values"]} for d in data]
        return sheets.batch_update(spreadsheet_id, qualified, value_input)

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

    def format(self, range: str | list[str], cell_format: "dict | CellFormat") -> None:
        """
        Format one or more ranges with a CellFormat object or a raw API dict.

        Example:
            ws.format("A1:Z1", CellFormat(text_format=TextFormat(bold=True)))
            ws.format("B2:B100", {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
        """
        if not isinstance(cell_format, dict):
            self._ctx.format_range(range, cell_format)
            return
        sheets, spreadsheet_id = self._client()
        for target in [range] if isinstance(range, str) else range:
            sheets.format_range(spreadsheet_id, self.id, target, cell_format)

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
        sheets._forget(spreadsheet_id)
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

    # ========== Tables and typed rows (engine) ==========

    def iter_rows(self, page_size: int = 1000, skiprows: int = 0) -> "Iterator[list[str]]":
        """Yield rows lazily, reading ``page_size`` rows per request (big sheets)."""
        return self._ctx.iter_rows(page_size=page_size, skiprows=skiprows)  # type: ignore[no-any-return]

    def iter_records(self, page_size: int = 1000) -> "Iterator[dict[str, str]]":
        """Yield rows as ``{header: value}`` dicts, lazily (header in row 1)."""
        return self._ctx.iter_records(page_size=page_size)  # type: ignore[no-any-return]

    def last_row(self) -> int:
        """Index (1-based) of the last row with data; 0 when empty."""
        return int(self._ctx.last_row())

    def update_row(self, row: int, values: list[Any], start_column: int | None = None) -> None:
        """Write ``values`` into ``row`` starting at ``start_column`` (1-based, default A)."""
        self._ctx.update_row(row, values, start_column=start_column)

    def insert(
        self,
        values: list[list[Any]],
        row: int | None = None,
        value_input: "ValueInput" = "USER_ENTERED",
    ) -> Any:
        """
        Insert rows at ``row`` (1-based), shifting the existing ones down; append when None.

        GSpreadManager's insert(fila=...) appended after the table instead: it
        sent values.append with a range starting at that row, which the API
        treats as "find the table there and add after it".
        """
        if row is None:
            return self.append_rows(values, value_input)
        self.insert_rows(row, len(values))
        return self.update(f"A{row}", values, value_input)

    def import_csv(self, source: Any, *, clear: bool = True, delimiter: str = ",") -> Any:
        """Load a CSV (path or file object) from A1, clearing the sheet first unless clear=False."""
        return self._ctx.import_csv(source, clear=clear, delimiter=delimiter)

    def upsert(self, rows: list[dict[str, Any]] | list[list[Any]], key: str) -> dict[str, int]:
        """
        Update rows whose ``key`` column matches and append the rest.

        Returns:
            {"updated": n, "appended": m}
        """
        return dict(self._ctx.upsert(rows, key))

    def update_where(self, where: "Where", updates: dict[str, Any]) -> int:
        """Set ``updates`` on rows matching ``where`` ({column: value} or a predicate)."""
        return int(self._ctx.update_where(where, updates))

    def delete_where(self, where: "Where") -> int:
        """Delete rows matching ``where``; returns how many were deleted."""
        return int(self._ctx.delete_where(where))

    def rows_where_column_equals(self, column: int, value: Any) -> list[tuple[int, list[str]]]:
        """(row number, row) for rows whose ``column`` (0-based, as in GSpreadManager) equals ``value``."""
        return list(self._ctx.rows_where_column_equals(column, value))

    def row_with_empty_in_column(self, column_letter: str) -> tuple[list[Any] | None, int | None]:
        """First row with an empty cell in ``column_letter``: (row values, number) or (None, None)."""
        result: tuple[list[Any] | None, int | None] = self._ctx.row_with_empty_in_column(
            column_letter
        )
        return result

    def ensure_schema(
        self, model: type, *, create: bool = True, strict: bool = False
    ) -> dict[str, Any]:
        """Check (or write, if the sheet is empty) the header row against ``model``'s fields."""
        return dict(self._ctx.ensure_schema(model, create=create, strict=strict))

    def read_as(self, model: type, skiprows: int = 0) -> list[Any]:
        """Rows as ``model`` instances (dataclass or Pydantic), with values converted to field types."""
        return list(self._ctx.read_as(model, skiprows=skiprows))

    def iter_as(self, model: type, page_size: int = 1000) -> "Iterator[Any]":
        """Like read_as(), lazily."""
        return self._ctx.iter_as(model, page_size=page_size)  # type: ignore[no-any-return]

    def append_models(self, models: list[Any]) -> Any:
        """Append model instances as rows."""
        return self._ctx.append_models(models)

    def write_models(
        self, models: list[Any], include_header: bool = True, clear: bool = True
    ) -> Any:
        """Write model instances from A1 (header from the fields)."""
        return self._ctx.write_models(models, include_header=include_header, clear=clear)

    def upsert_models(self, models: list[Any], key: str) -> dict[str, int]:
        """upsert() for model instances."""
        return dict(self._ctx.upsert_models(models, key))

    # ========== More formatting (engine) ==========

    def format_header(self, range: str = "1:1", background_hex: str | None = "#D9EAD3") -> None:
        """Bold header with a background color."""
        self._ctx.format_header(range, background_hex)

    def set_background(self, range: str | list[str], color: "Color") -> None:
        """Background color for one or more ranges."""
        self._ctx.set_background(range, color)

    def set_text_format(
        self,
        range: str | list[str],
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        font_size: int | None = None,
        color: "Color | None" = None,
    ) -> None:
        """Bold, italic, size and/or color of the text."""
        self._ctx.set_text_format(range, bold=bold, italic=italic, font_size=font_size, color=color)

    def set_number_format(
        self, range: str | list[str], pattern: str, number_type: str = "NUMBER"
    ) -> None:
        """Number format, e.g. ("C2:C100", "#,##0.00", "CURRENCY")."""
        self._ctx.set_number_format(range, pattern, number_type)

    def merge(self, range: str, merge_type: str = "MERGE_ALL") -> None:
        """Merge cells (MERGE_ALL, MERGE_ROWS or MERGE_COLUMNS)."""
        self._ctx.merge(range, merge_type)

    def unmerge(self, range: str) -> None:
        """Undo merges in a range."""
        self._ctx.unmerge(range)

    def set_tab_color(self, color: "Color") -> None:
        """Color of the tab."""
        self._ctx.set_tab_color(color)

    def clear_tab_color(self) -> None:
        """Remove the tab color."""
        self._ctx.clear_tab_color()

    # ========== Data validation and conditional formatting (engine) ==========

    def add_dropdown(self, range: str, values: list[Any], strict: bool = True) -> None:
        """Dropdown with ``values``; ``strict`` rejects anything else."""
        self._ctx.add_dropdown(range, values, strict)

    def add_checkbox(self, range: str) -> None:
        """Checkboxes."""
        self._ctx.add_checkbox(range)

    def set_data_validation(
        self,
        range: str,
        condition_type: str,
        values: list[Any] | None = None,
        strict: bool = True,
        show_custom_ui: bool = True,
    ) -> None:
        """Any validation rule, e.g. ("B2:B100", "NUMBER_GREATER", [0])."""
        self._ctx.set_data_validation(range, condition_type, values, strict, show_custom_ui)

    def add_conditional_format(
        self,
        range: str,
        condition_type: str,
        values: list[Any],
        cell_format: "CellFormat",
        index: int = 0,
    ) -> None:
        """Format cells meeting a condition, e.g. ("C2:C100", "NUMBER_LESS", [0], red)."""
        self._ctx.add_conditional_format(range, condition_type, values, cell_format, index)

    # ========== Rows, columns, sorting and filters (engine) ==========

    def insert_rows(self, at: int, number: int = 1, inherit_from_before: bool = False) -> None:
        """Insert blank rows before row ``at`` (1-based)."""
        self._ctx.insert_rows(at, number, inherit_from_before)

    def insert_cols(self, at: int, number: int = 1, inherit_from_before: bool = False) -> None:
        """Insert blank columns before column ``at`` (1-based)."""
        self._ctx.insert_cols(at, number, inherit_from_before)

    def delete_rows(self, start: int, end: int | None = None) -> None:
        """Delete rows start..end (1-based, inclusive)."""
        self._ctx.delete_rows(start, end)

    def delete_cols(self, start: int, end: int | None = None) -> None:
        """Delete columns start..end (1-based, inclusive)."""
        self._ctx.delete_cols(start, end)

    def add_rows(self, number: int) -> None:
        """Grow the grid by ``number`` rows."""
        self._ctx.add_rows(number)

    def add_cols(self, number: int) -> None:
        """Grow the grid by ``number`` columns."""
        self._ctx.add_cols(number)

    def resize_rows(self, start: int, end: int, pixels: int) -> None:
        """Row height for rows start..end."""
        self._ctx.resize_rows(start, end, pixels)

    def resize_cols(self, start: int, end: int, pixels: int) -> None:
        """Column width for columns start..end."""
        self._ctx.resize_cols(start, end, pixels)

    def hide_rows(self, start: int, end: int | None = None) -> None:
        """Hide rows."""
        self._ctx.hide_rows(start, end)

    def unhide_rows(self, start: int, end: int | None = None) -> None:
        """Show hidden rows."""
        self._ctx.unhide_rows(start, end)

    def hide_cols(self, start: int, end: int | None = None) -> None:
        """Hide columns."""
        self._ctx.hide_cols(start, end)

    def unhide_cols(self, start: int, end: int | None = None) -> None:
        """Show hidden columns."""
        self._ctx.unhide_cols(start, end)

    def sort_range(self, range: str, *specs: tuple[int, str]) -> None:
        """Sort by columns: sort_range("A2:C100", (1, "asc"), (3, "desc"))."""
        self._ctx.sort_range(range, *specs)

    def set_basic_filter(self, range: str | None = None) -> None:
        """Turn on the filter (whole sheet by default)."""
        self._ctx.set_basic_filter(range)

    def clear_basic_filter(self) -> None:
        """Turn off the filter."""
        self._ctx.clear_basic_filter()

    def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copy this tab into another spreadsheet."""
        return self._ctx.copy_to(destination_spreadsheet_id)

    # ========== Notes, named and protected ranges, metadata (engine) ==========

    def update_note(self, cell: str, text: str) -> None:
        """Set a cell note."""
        self._ctx.update_note(cell, text)

    def clear_note(self, cell: str) -> None:
        """Remove a cell note."""
        self._ctx.clear_note(cell)

    def get_note(self, cell: str) -> str:
        """A cell's note ("" if none)."""
        return str(self._ctx.get_note(cell))

    def define_named_range(self, name: str, range: str) -> None:
        """Name a range of this sheet (see Spreadsheet.list_named_ranges)."""
        self._ctx.define_named_range(name, range)

    def list_protected_ranges(self) -> list[dict[str, Any]]:
        """Protected ranges of this sheet."""
        return list(self._ctx.list_protected_ranges())

    def delete_protected_range(self, protected_range_id: str | int) -> None:
        """Remove a protection (ID from protect() or list_protected_ranges())."""
        self._ctx.delete_protected_range(protected_range_id)

    def set_developer_metadata(self, key: str, value: str, visibility: str = "DOCUMENT") -> None:
        """Attach a key/value to this sheet (hidden from users)."""
        self._ctx.set_developer_metadata(key, value, visibility)

    # ========== Charts, pivot tables, banding (engine) ==========

    def add_chart(
        self,
        chart_type: str,
        domain: str,
        series: list[str],
        *,
        title: str | None = None,
        anchor_cell: str = "A1",
        legend: str = "BOTTOM_LEGEND",
    ) -> int | None:
        """Embedded chart (COLUMN, BAR, LINE, AREA, PIE, SCATTER, ...); returns its ID."""
        chart_id: int | None = self._ctx.add_chart(
            chart_type, domain, series, title=title, anchor_cell=anchor_cell, legend=legend
        )
        return chart_id

    def delete_chart(self, chart_id: int) -> None:
        """Remove an embedded chart."""
        self._ctx.delete_chart(chart_id)

    def add_pivot_table(
        self,
        source: str,
        anchor_cell: str,
        *,
        rows: list[int],
        values: list[tuple[int, str]],
        columns: list[int] | None = None,
    ) -> None:
        """Pivot table at ``anchor_cell`` over ``source``; values are (column, "SUM"|"COUNTA"|...)."""
        self._ctx.add_pivot_table(source, anchor_cell, rows=rows, values=values, columns=columns)

    def set_banding(
        self,
        range: str,
        *,
        first_color: "Color",
        second_color: "Color",
        header_color: "Color | None" = None,
    ) -> int | None:
        """Alternating row colors; returns the banding ID."""
        banding_id: int | None = self._ctx.set_banding(
            range, first_color=first_color, second_color=second_color, header_color=header_color
        )
        return banding_id

    def delete_banding(self, banded_range_id: int) -> None:
        """Remove alternating colors."""
        self._ctx.delete_banding(banded_range_id)

    # ========== DataFrames (engine: pandas or polars) ==========

    def read_dataframe(
        self,
        skiprows: int = 0,
        *,
        drop_empty_rows: bool = False,
        drop_empty_cols: bool = False,
        index_col: str | None = None,
    ) -> Any:
        """
        The sheet as a DataFrame of the client's backend (Sheets(dataframe_backend=...)).

        Needs gsuite-sdk[pandas] or gsuite-sdk[polars].
        """
        return self._ctx.read_dataframe(
            skiprows,
            drop_empty_rows=drop_empty_rows,
            drop_empty_cols=drop_empty_cols,
            index_col=index_col,
        )

    def write_dataframe(
        self,
        df: Any,
        include_header: bool = True,
        clear: bool = True,
        *,
        start_cell: str | None = None,
        include_index: bool = False,
    ) -> Any:
        """Write a pandas or polars DataFrame (from A1 or ``start_cell``)."""
        return self._ctx.write_dataframe(
            df, include_header, clear, start_cell=start_cell, include_index=include_index
        )

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
