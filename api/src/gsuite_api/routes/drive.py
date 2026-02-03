"""Drive API routes."""

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel

router = APIRouter()


class FileResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    web_view_link: str | None


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


@router.get("/files")
async def list_files(
    query: str | None = Query(None, description="Drive search query"),
    parent_id: str | None = Query(None, description="Parent folder ID"),
    limit: int = Query(100, le=1000),
):
    """
    List Drive files.

    Note: Drive routes are placeholders. Install gsuite-drive and configure auth.
    """
    return {
        "status": "placeholder",
        "message": "Drive API coming soon. Install gsuite-drive package.",
        "files": [],
    }


@router.get("/files/{file_id}")
async def get_file(file_id: str):
    """Get a specific file."""
    return {
        "status": "placeholder",
        "message": "Drive API coming soon",
    }


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    parent_id: str | None = None,
):
    """Upload a file."""
    return {
        "status": "placeholder",
        "message": "Drive API coming soon",
        "filename": file.filename,
    }


@router.post("/folders")
async def create_folder(request: CreateFolderRequest):
    """Create a folder."""
    return {
        "status": "placeholder",
        "message": "Drive API coming soon",
        "name": request.name,
    }


@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """Delete a file."""
    return {
        "status": "placeholder",
        "message": "Drive API coming soon",
    }


@router.post("/files/{file_id}/share")
async def share_file(
    file_id: str,
    email: str = Query(...),
    role: str = Query("reader"),
):
    """Share a file."""
    return {
        "status": "placeholder",
        "message": "Drive API coming soon",
    }
