"""Sheets API routes."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import SheetsDep
from gsuite_api.responses import download_response
from gsuite_sheets import CellFormat, Color, TextFormat
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


class UpsertRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(..., min_length=1, description="Records keyed by header")
    key: str = Field(..., description="Header of the column that identifies a row")


class DropdownRequest(BaseModel):
    range: str
    values: list[Any] = Field(..., min_length=1)
    strict: bool = True


class RangeRequest(BaseModel):
    range: str


class ConditionalFormatRequest(BaseModel):
    range: str
    condition_type: str = Field(..., examples=["NUMBER_LESS", "TEXT_CONTAINS", "CUSTOM_FORMULA"])
    values: list[Any] = Field(default_factory=list)
    background: str | None = Field(None, description="Hex color, e.g. #F4CCCC")
    text_color: str | None = Field(None, description="Hex color")
    bold: bool | None = None


class MergeRequest(BaseModel):
    range: str
    merge_type: Literal["MERGE_ALL", "MERGE_ROWS", "MERGE_COLUMNS"] = "MERGE_ALL"


class SortRequest(BaseModel):
    range: str
    by: list[tuple[int, Literal["asc", "desc"]]] = Field(
        ..., min_length=1, description='[[column (1-based), "asc"|"desc"], ...]'
    )


class DimensionRequest(BaseModel):
    dimension: Literal["rows", "columns"]
    start: int = Field(..., ge=1, description="1-based")
    count: int = Field(1, ge=1)


def _open_worksheet(sheets: Any, spreadsheet_id: str, sheet_id: int) -> Worksheet:
    ws = sheets.open_by_key(spreadsheet_id).worksheet_by_id(sheet_id)
    if ws is None:
        raise HTTPException(status_code=404, detail=f"Worksheet {sheet_id} not found")
    ws_typed: Worksheet = ws
    return ws_typed


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


# ========== Engine features ==========

EXPORT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/x-vnd.oasis.opendocument.spreadsheet",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "html": "application/zip",
}


@router.get("/{spreadsheet_id}/export")
def export_spreadsheet(
    sheets: SheetsDep,
    spreadsheet_id: str,
    format: Literal["pdf", "xlsx", "ods", "csv", "tsv", "html"] = Query("pdf"),
) -> Any:
    """Download the spreadsheet (csv/tsv export only the first sheet; html is a zip)."""
    doc = sheets.open_by_key(spreadsheet_id)
    content = doc.export(format)
    extension = "zip" if format == "html" else format
    return download_response(content, f"{doc.title}.{extension}", EXPORT_TYPES[format])


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/upsert")
def upsert(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: UpsertRequest
) -> dict[str, Any]:
    """Update rows whose ``key`` column matches, append the rest."""
    result = _open_worksheet(sheets, spreadsheet_id, sheet_id).upsert(request.rows, request.key)
    return {"id": sheet_id, **result}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/dropdown")
def add_dropdown(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: DropdownRequest
) -> dict[str, Any]:
    """Dropdown validation on a range."""
    _open_worksheet(sheets, spreadsheet_id, sheet_id).add_dropdown(
        request.range, request.values, request.strict
    )
    return {"id": sheet_id, "range": request.range}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/checkbox")
def add_checkbox(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: RangeRequest
) -> dict[str, Any]:
    """Checkboxes on a range."""
    _open_worksheet(sheets, spreadsheet_id, sheet_id).add_checkbox(request.range)
    return {"id": sheet_id, "range": request.range}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/conditional-format")
def add_conditional_format(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: ConditionalFormatRequest
) -> dict[str, Any]:
    """Format cells meeting a condition (background, text color, bold)."""
    text = None
    if request.bold is not None or request.text_color:
        text = TextFormat(
            bold=request.bold,
            foreground_color=Color.from_hex(request.text_color) if request.text_color else None,
        )
    cell_format = CellFormat(
        background_color=Color.from_hex(request.background) if request.background else None,
        text_format=text,
    )
    _open_worksheet(sheets, spreadsheet_id, sheet_id).add_conditional_format(
        request.range, request.condition_type, request.values, cell_format
    )
    return {"id": sheet_id, "range": request.range}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/merge")
def merge(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: MergeRequest
) -> dict[str, Any]:
    """Merge cells."""
    _open_worksheet(sheets, spreadsheet_id, sheet_id).merge(request.range, request.merge_type)
    return {"id": sheet_id, "range": request.range, "merged": True}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/unmerge")
def unmerge(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: RangeRequest
) -> dict[str, Any]:
    """Undo merges in a range."""
    _open_worksheet(sheets, spreadsheet_id, sheet_id).unmerge(request.range)
    return {"id": sheet_id, "range": request.range, "merged": False}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/sort")
def sort(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: SortRequest
) -> dict[str, Any]:
    """Sort a range by one or more columns."""
    _open_worksheet(sheets, spreadsheet_id, sheet_id).sort_range(request.range, *request.by)
    return {"id": sheet_id, "range": request.range}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/dimensions:insert")
def insert_dimension(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: DimensionRequest
) -> dict[str, Any]:
    """Insert blank rows or columns before ``start``."""
    ws = _open_worksheet(sheets, spreadsheet_id, sheet_id)
    insert = ws.insert_rows if request.dimension == "rows" else ws.insert_cols
    insert(request.start, request.count)
    return {"id": sheet_id, "inserted": request.count, "dimension": request.dimension}


@router.post("/{spreadsheet_id}/worksheets/{sheet_id}/dimensions:delete")
def delete_dimension(
    sheets: SheetsDep, spreadsheet_id: str, sheet_id: int, request: DimensionRequest
) -> dict[str, Any]:
    """Delete ``count`` rows or columns starting at ``start``."""
    ws = _open_worksheet(sheets, spreadsheet_id, sheet_id)
    delete = ws.delete_rows if request.dimension == "rows" else ws.delete_cols
    delete(request.start, request.start + request.count - 1)
    return {"id": sheet_id, "deleted": request.count, "dimension": request.dimension}
