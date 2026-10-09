"""Sheets API routes."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from gsuite_api.dependencies import SheetsDep

router = APIRouter()


class UpdateRequest(BaseModel):
    range: str
    values: list[list[Any]]


class AppendRequest(BaseModel):
    values: list[list[Any]]


class BatchUpdateRequest(BaseModel):
    data: list[UpdateRequest]


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
):
    """Update values in a range."""
    result = sheets.update_values(spreadsheet_id, range, request.values)
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
):
    """Append values to a sheet."""
    result = sheets.append_values(spreadsheet_id, sheet_name, request.values)
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
):
    """Batch update multiple ranges."""
    data = [{"range": d.range, "values": d.values} for d in request.data]
    result = sheets.batch_update(spreadsheet_id, data)
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
