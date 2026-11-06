"""Sheets tools: read, append, update and upsert rows."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    DESTRUCTIVE,
    READ,
    WRITE,
    ToolDecorator,
)

# Longer than this is taken as a spreadsheet ID (IDs are 44 characters), not a title
_ID_HINT_LENGTH = 30


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the sheets tools on the server."""

    def open_spreadsheet(spreadsheet: str) -> Any:
        """By URL, ID or exact title."""
        if spreadsheet.startswith("http"):
            return svc.sheets.open_by_url(spreadsheet)
        if len(spreadsheet) > _ID_HINT_LENGTH:
            return svc.sheets.open_by_key(spreadsheet)
        return svc.sheets.open(spreadsheet)

    def worksheet(spreadsheet: str, sheet: str | None) -> Any:
        doc = open_spreadsheet(spreadsheet)
        ws = doc.worksheet(sheet) if sheet else doc.sheet1
        if ws is None:
            raise ToolError(f"No tab {sheet!r} in {doc.title}")
        return ws

    @tool(READ)
    def sheets_read(
        spreadsheet: str, range: str = "A1:Z200", sheet: str | None = None
    ) -> dict[str, Any]:
        """Read a range. `spreadsheet` is a URL, an ID or an exact title; `sheet`
        is the tab (default: the first one). Values come back as displayed.
        """
        ws = worksheet(spreadsheet, sheet)
        return {"sheet": ws.title, "range": range, "values": ws.get(range)}

    @tool(WRITE)
    def sheets_append(
        spreadsheet: str, rows: list[list[Any]], sheet: str | None = None
    ) -> dict[str, Any]:
        """Append rows after the last one with data."""
        ws = worksheet(spreadsheet, sheet)
        ws.append_rows(rows)
        return {"sheet": ws.title, "appended": len(rows)}

    @tool(DESTRUCTIVE)
    def sheets_update(
        spreadsheet: str, range: str, values: list[list[Any]], sheet: str | None = None
    ) -> dict[str, Any]:
        """Overwrite a range starting at `range` (e.g. "B2") with a 2D list of values."""
        ws = worksheet(spreadsheet, sheet)
        ws.update(range, values)
        return {"sheet": ws.title, "range": range, "rows": len(values)}

    @tool(WRITE)
    def sheets_upsert(
        spreadsheet: str, rows: list[dict[str, Any]], key: str, sheet: str | None = None
    ) -> dict[str, Any]:
        """Update the rows whose `key` column matches and append the rest.
        The first row of the sheet is the header; rows are {column: value}.
        """
        ws = worksheet(spreadsheet, sheet)
        return dict(ws.upsert(rows, key=key))
