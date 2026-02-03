"""Sheets API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from gsuite_api.dependencies import get_auth
from gsuite_core import GoogleAuth
from gsuite_sheets import Sheets

router = APIRouter()


def get_sheets(auth: Annotated[GoogleAuth, Depends(get_auth)]) -> Sheets:
    """Get authenticated Sheets client."""
    if not auth.is_authenticated():
        if auth.needs_refresh():
            if not auth.refresh():
                raise HTTPException(
                    status_code=401,
                    detail="Token expired. Re-authenticate required.",
                )
        else:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated. Run OAuth flow first.",
            )
    return Sheets(auth)


SheetsDep = Annotated[Sheets, Depends(get_sheets)]


class UpdateRequest(BaseModel):
    range: str
    values: list[list[Any]]


class AppendRequest(BaseModel):
    values: list[list[Any]]


class BatchUpdateRequest(BaseModel):
    data: list[UpdateRequest]


@router.get("/list")
async def list_spreadsheets(
    sheets: SheetsDep,
    limit: int = Query(50, le=100),
):
    """List all spreadsheets accessible to the user."""
    try:
        spreadsheets = sheets.list_spreadsheets(max_results=limit)
        return {
            "count": len(spreadsheets),
            "spreadsheets": spreadsheets,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{spreadsheet_id}")
async def get_spreadsheet(
    sheets: SheetsDep,
    spreadsheet_id: str,
):
    """Get spreadsheet metadata and worksheets."""
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{spreadsheet_id}/values/{range:path}")
async def get_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
):
    """Get values from a range (e.g., Sheet1!A1:D10)."""
    try:
        values = sheets.get_values(spreadsheet_id, range)
        return {
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "values": values,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{spreadsheet_id}/values/{range:path}")
async def update_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
    request: UpdateRequest,
):
    """Update values in a range."""
    try:
        result = sheets.update_values(spreadsheet_id, range, request.values)
        return {
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "updated_cells": result.get("updatedCells", 0),
            "updated_rows": result.get("updatedRows", 0),
            "updated_columns": result.get("updatedColumns", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{spreadsheet_id}/values/{sheet_name}:append")
async def append_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    sheet_name: str,
    request: AppendRequest,
):
    """Append values to a sheet."""
    try:
        result = sheets.append_values(spreadsheet_id, sheet_name, request.values)
        return {
            "spreadsheet_id": spreadsheet_id,
            "sheet": sheet_name,
            "appended_rows": len(request.values),
            "updates": result.get("updates", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{spreadsheet_id}/values:batchUpdate")
async def batch_update(
    sheets: SheetsDep,
    spreadsheet_id: str,
    request: BatchUpdateRequest,
):
    """Batch update multiple ranges."""
    try:
        data = [{"range": d.range, "values": d.values} for d in request.data]
        result = sheets.batch_update(spreadsheet_id, data)
        return {
            "spreadsheet_id": spreadsheet_id,
            "updated_ranges": len(request.data),
            "responses": result.get("responses", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{spreadsheet_id}/values/{range:path}")
async def clear_values(
    sheets: SheetsDep,
    spreadsheet_id: str,
    range: str,
):
    """Clear values from a range."""
    try:
        sheets.clear_values(spreadsheet_id, range)
        return {
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "cleared": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_spreadsheet(
    sheets: SheetsDep,
    title: str = Query(...),
):
    """Create a new spreadsheet."""
    try:
        doc = sheets.create(title)
        return {
            "id": doc.id,
            "title": doc.title,
            "url": doc.url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
