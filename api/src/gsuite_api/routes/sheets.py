"""Sheets API routes."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import SheetsDep
from gsuite_sheets.a1 import a1
from gsuite_sheets.worksheet import Worksheet

router = APIRouter()

ValueInputQuery = Query(
    "USER_ENTERED",
    description="USER_ENTERED parses values like the UI (formulas, dates); "
    "RAW stores them as-is (use for untrusted text)",
)


class UpdateRequest(BaseModel):
    range: str
    values: list[list[Any]]


class AppendRequest(BaseModel):
    values: list[list[Any]]


class BatchUpdateRequest(BaseModel):
    data: list[UpdateRequest]


class WorksheetResponse(BaseModel):
    id: int
    title: str
    index: int
    row_count: int
    column_count: int


class AddWorksheetRequest(BaseModel):
    title: str
    rows: int = Field(1000, ge=1)
    cols: int = Field(26, ge=1)


class RenameWorksheetRequest(BaseModel):
    title: str


class DuplicateWorksheetRequest(BaseModel):
    title: str | None = None


class FormatRequest(BaseModel):
    range: str = Field(..., description='A1 range without the sheet, e.g. "A1:Z1"')
    format: dict[str, Any] = Field(..., description="Sheets CellFormat")


class FreezeRequest(BaseModel):
    rows: int | None = Field(None, ge=0)
    cols: int | None = Field(None, ge=0)


class ProtectRequest(BaseModel):
    range: str | None = Field(None, description="A1 range; omit to protect the whole sheet")
    description: str | None = None
    editors: list[EmailStr] | None = None
    warning_only: bool = False


class FindReplaceRequest(BaseModel):
    find: str
    replacement: str
    sheet_id: int | None = Field(None, description="Omit to search every sheet")
    match_case: bool = False
    match_entire_cell: bool = False
    regex: bool = False


def _worksheet(ws: Worksheet) -> WorksheetResponse:
    return WorksheetResponse(
        id=ws.id,
        title=ws.title,
        index=ws.index,
        row_count=ws.row_count,
        column_count=ws.column_count,
    )


@router.get("/list")
def list_spreadsheets(
    sheets: SheetsDep,
    limit: int = Query(50, le=100),
):
    """List all spreadsheets accessible to the user."""
    spreadsheets = sheets.list_spreadsheets(max_results=limit)
    return {
        "count": len(spreadsheets),
        "spreadsheets": spreadsheets,
    }


@router.get("/{spreadsheet_id}")
def get_spreadsheet(
    sheets: SheetsDep,
    spreadsheet_id: str,
):
    """Get spreadsheet metadata and worksheets."""
    doc = sheets.open_by_key(spreadsheet_id)
    return {
        "id": doc.id,
        "title": doc.title,
        "url": doc.url,
        "locale": doc.locale,
        "time_zone": doc.time_zone,
        "worksheets": [
            {
                "id": ws.id,
                "title": ws.title,
                "index": ws.index,
                "row_count": ws.row_count,
                "column_count": ws.column_count,
            }
            for ws in doc.worksheets
        ],
    }


@router.get("/{spreadsheet_id}/values/{range:path}")
def get_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
):
    """Get values from a range (e.g., Sheet1!A1:D10)."""
    values = sheets.get_values(spreadsheet_id, range)
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range,
        "values": values,
    }


@router.put("/{spreadsheet_id}/values/{range:path}")
def update_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
    request: UpdateRequest,
    value_input: Literal["USER_ENTERED", "RAW"] = ValueInputQuery,
):
    """Update values in a range."""
    result = sheets.update_values(spreadsheet_id, range, request.values, value_input)
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range,
        "updated_cells": result.get("updatedCells", 0),
        "updated_rows": result.get("updatedRows", 0),
        "updated_columns": result.get("updatedColumns", 0),
    }


@router.post("/{spreadsheet_id}/values/{sheet_name}:append")
def append_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    sheet_name: str,
    request: AppendRequest,
    value_input: Literal["USER_ENTERED", "RAW"] = ValueInputQuery,
):
    """Append values to a sheet."""
    # Quoted so sheet names like "2024" or "Q1 Budget" resolve to the sheet
    result = sheets.append_values(spreadsheet_id, a1(sheet_name), request.values, value_input)
    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet": sheet_name,
        "appended_rows": len(request.values),
        "updates": result.get("updates", {}),
    }


@router.post("/{spreadsheet_id}/values:batchUpdate")
def batch_update(
    sheets: SheetsDep,
    spreadsheet_id: str,
    request: BatchUpdateRequest,
    value_input: Literal["USER_ENTERED", "RAW"] = ValueInputQuery,
):
    """Batch update multiple ranges."""
    data = [{"range": d.range, "values": d.values} for d in request.data]
    result = sheets.batch_update(spreadsheet_id, data, value_input)
    return {
        "spreadsheet_id": spreadsheet_id,
        "updated_ranges": len(request.data),
        "responses": result.get("responses", []),
    }


@router.delete("/{spreadsheet_id}/values/{range:path}")
def clear_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
):
    """Clear values from a range."""
    sheets.clear_values(spreadsheet_id, range)
    return {
        "spreadsheet_id": spreadsheet_id,
        "range": range,
        "cleared": True,
    }


@router.post("/create")
def create_spreadsheet(
    sheets: SheetsDep,
    title: str = Query(...),
):
    """Create a new spreadsheet."""
    doc = sheets.create(title)
    return {
        "id": doc.id,
        "title": doc.title,
        "url": doc.url,
    }


@router.get("/{spreadsheet_id}/values:batchGet")
def batch_get(
    sheets: SheetsDep,
    spreadsheet_id: str,
    ranges: list[str] = Query(
        ..., description="A1 ranges, e.g. ranges=Sheet1!A1:B2&ranges=Sheet2!C:C"
    ),
) -> dict[str, Any]:
    """Read several ranges in one call."""
    values = sheets.batch_get_values(spreadsheet_id, ranges)
    return {
        "spreadsheet_id": spreadsheet_id,
        "value_ranges": [{"range": r, "values": v} for r, v in zip(ranges, values)],
    }


@router.post("/{spreadsheet_id}:findReplace")
def find_replace(
    sheets: SheetsDep, spreadsheet_id: str, request: FindReplaceRequest
) -> dict[str, Any]:
    """Find and replace text in one sheet or all of them."""
    changed = sheets.find_replace(
        spreadsheet_id,
        request.find,
        request.replacement,
        sheet_id=request.sheet_id,
        match_case=request.match_case,
        match_entire_cell=request.match_entire_cell,
        regex=request.regex,
    )
    return {"spreadsheet_id": spreadsheet_id, "occurrences_changed": changed}


# ========== Worksheets ==========


@router.post("/{spreadsheet_id}/worksheets")
def add_worksheet(
    sheets: SheetsDep, spreadsheet_id: str, request: AddWorksheetRequest
) -> WorksheetResponse:
    """Add a worksheet (tab)."""
    return _worksheet(
        sheets.add_worksheet(spreadsheet_id, request.title, request.rows, request.cols)
    )


@router.patch("/{spreadsheet_id}/worksheets/{sheet_id}")
def rename_worksheet(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: RenameWorksheetRequest
) -> dict[str, Any]:
    """Rename a worksheet."""
    sheets.rename_worksheet(spreadsheet_id, sheet_id, request.title)
    return {"id": sheet_id, "title": request.title}


@router.delete("/{spreadsheet_id}/worksheets/{sheet_id}")
def delete_worksheet(sheets: SheetsDep, spreadsheet_id: str, sheet_id: int) -> dict[str, Any]:
    """Delete a worksheet. Deleting the last one fails (400 from Google)."""
    if not sheets.delete_worksheet(spreadsheet_id, sheet_id):
        raise HTTPException(status_code=404, detail="Spreadsheet not found")
    return {"id": sheet_id, "deleted": True}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/duplicate")
def duplicate_worksheet(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: DuplicateWorksheetRequest
) -> WorksheetResponse:
    """Copy a worksheet within the spreadsheet."""
    return _worksheet(sheets.duplicate_worksheet(spreadsheet_id, sheet_id, request.title))


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/format")
def format_range(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: FormatRequest
) -> dict[str, Any]:
    """Apply a cell format to a range."""
    sheets.format_range(spreadsheet_id, sheet_id, request.range, request.format)
    return {"id": sheet_id, "range": request.range, "formatted": True}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/freeze")
def freeze(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: FreezeRequest
) -> dict[str, Any]:
    """Freeze header rows and/or columns."""
    sheets.freeze(spreadsheet_id, sheet_id, request.rows, request.cols)
    return {"id": sheet_id, "rows": request.rows, "cols": request.cols}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/protect")
def protect(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: ProtectRequest
) -> dict[str, Any]:
    """Protect a range or the whole worksheet."""
    protected_id = sheets.protect_range(
        spreadsheet_id,
        sheet_id,
        request.range,
        request.description,
        [str(e) for e in request.editors] if request.editors else None,
        request.warning_only,
    )
    return {"id": sheet_id, "protected_range_id": protected_id}
