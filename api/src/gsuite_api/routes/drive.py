"""Drive API routes."""

from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, EmailStr

from gsuite_api.dependencies import DriveDep
from gsuite_api.responses import download_response
from gsuite_drive import EXPORT_FORMATS
from gsuite_drive import File as DriveFile
from gsuite_drive.client import default_export_format

router = APIRouter()


# ========== Models ==========


class FileResponse(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int
    parents: list[str]
    created_time: str | None
    modified_time: str | None
    description: str | None
    starred: bool
    trashed: bool
    web_view_link: str | None


class PermissionResponse(BaseModel):
    id: str
    type: str
    role: str
    email_address: str | None
    domain: str | None
    display_name: str | None


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


class UpdateFileRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    starred: bool | None = None


class CopyRequest(BaseModel):
    name: str | None = None
    parent_id: str | None = None


class MoveRequest(BaseModel):
    parent_id: str


class PermissionRequest(BaseModel):
    role: Literal["reader", "commenter", "writer"] = "reader"
    type: Literal["user", "group", "domain", "anyone"] = "user"
    email: EmailStr | None = None
    domain: str | None = None
    notify: bool = True


def _file(f: DriveFile) -> FileResponse:
    return FileResponse(
        id=f.id,
        name=f.name,
        mime_type=f.mime_type,
        size=f.size,
        parents=f.parents,
        created_time=f.created_time.isoformat() if f.created_time else None,
        modified_time=f.modified_time.isoformat() if f.modified_time else None,
        description=f.description,
        starred=f.starred,
        trashed=f.trashed,
        web_view_link=f.web_view_link,
    )


def _require(file: DriveFile | None) -> DriveFile:
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file


# ========== Files ==========


@router.get("/files")
def list_files(
    drive: DriveDep,
    query: str | None = Query(None, description="Raw Drive search query (q)"),
    parent_id: str | None = Query(None, description="Parent folder ID"),
    mime_type: str | None = Query(None, description="Filter by MIME type"),
    trashed: bool = Query(False, description="List trashed files instead"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """List files, newest first."""
    files = drive.list_files(
        query=query, parent_id=parent_id, mime_type=mime_type, max_results=limit, trashed=trashed
    )
    return {"files": [_file(f) for f in files], "count": len(files)}


@router.post("/files/upload")
def upload_file(
    drive: DriveDep,
    file: UploadFile = File(...),
    parent_id: str | None = Form(None),
    name: str | None = Form(None, description="Name in Drive (default: uploaded filename)"),
) -> FileResponse:
    """Upload a file (multipart/form-data)."""
    uploaded = drive.upload_content(
        file.file,
        name=name or file.filename or "upload",
        parent_id=parent_id,
        mime_type=file.content_type or "application/octet-stream",
    )
    return _file(uploaded)


@router.get("/files/{file_id}")
def get_file(file_id: str, drive: DriveDep) -> FileResponse:
    """Get file metadata."""
    return _file(_require(drive.get(file_id)))


@router.get("/files/{file_id}/content")
def download_file(
    file_id: str,
    drive: DriveDep,
    export: str | None = Query(
        None,
        description=f"Export format for Google files: {', '.join(sorted(EXPORT_FORMATS))}",
    ),
) -> Response:
    """
    Download file content.

    Google Docs/Sheets/Slides are exported (docx/xlsx/pptx unless `export`
    says otherwise; Drive caps exports at 10 MB).
    """
    file = _require(drive.get(file_id))
    if file.is_google_doc or export:
        fmt = export or default_export_format(file.mime_type)
        content = drive.export(file_id, fmt)
        return download_response(
            content, f"{file.name}.{fmt}", EXPORT_FORMATS.get(fmt.lower(), fmt)
        )
    return download_response(drive.get_content(file_id), file.name, file.mime_type)


@router.patch("/files/{file_id}")
def update_file(file_id: str, request: UpdateFileRequest, drive: DriveDep) -> FileResponse:
    """Rename, describe or star a file. Only the fields you send change."""
    return _file(drive.update(file_id, **request.model_dump(exclude_none=True)))


@router.post("/files/{file_id}/copy")
def copy_file(file_id: str, request: CopyRequest, drive: DriveDep) -> FileResponse:
    """Copy a file."""
    return _file(drive.copy(file_id, name=request.name, parent_id=request.parent_id))


@router.post("/files/{file_id}/move")
def move_file(file_id: str, request: MoveRequest, drive: DriveDep) -> FileResponse:
    """Move a file to another folder."""
    return _file(drive.move(file_id, request.parent_id))


@router.post("/files/{file_id}/trash")
def trash_file(file_id: str, drive: DriveDep) -> dict[str, Any]:
    """Move a file to the trash."""
    if not drive.trash(file_id):
        raise HTTPException(status_code=404, detail="File not found")
    return {"id": file_id, "trashed": True}


@router.post("/files/{file_id}/restore")
def restore_file(file_id: str, drive: DriveDep) -> dict[str, Any]:
    """Restore a file from the trash."""
    if not drive.restore(file_id):
        raise HTTPException(status_code=404, detail="File not found")
    return {"id": file_id, "trashed": False}


@router.delete("/files/{file_id}")
def delete_file(
    file_id: str,
    drive: DriveDep,
    permanent: bool = Query(False, description="Delete forever instead of trashing"),
) -> dict[str, Any]:
    """Trash a file, or delete it permanently with `permanent=true`."""
    found = drive.delete(file_id) if permanent else drive.trash(file_id)
    if not found:
        raise HTTPException(status_code=404, detail="File not found")
    return {"id": file_id, "deleted": permanent, "trashed": not permanent}


# ========== Folders ==========


@router.post("/folders")
def create_folder(request: CreateFolderRequest, drive: DriveDep) -> FileResponse:
    """Create a folder."""
    return _file(drive.create_folder(request.name, parent_id=request.parent_id))


# ========== Permissions ==========


@router.get("/files/{file_id}/permissions")
def list_permissions(file_id: str, drive: DriveDep) -> dict[str, Any]:
    """List who can access a file."""
    perms = drive.list_permissions(file_id)
    return {
        "permissions": [PermissionResponse(**vars(p)) for p in perms],
        "count": len(perms),
    }


@router.post("/files/{file_id}/permissions")
def add_permission(file_id: str, request: PermissionRequest, drive: DriveDep) -> PermissionResponse:
    """Share a file with a user, group, domain or anyone with the link."""
    perm = drive.add_permission(
        file_id,
        role=request.role,
        type=request.type,
        email=str(request.email) if request.email else None,
        domain=request.domain,
        notify=request.notify,
    )
    return PermissionResponse(**vars(perm))


@router.delete("/files/{file_id}/permissions/{permission_id}")
def remove_permission(file_id: str, permission_id: str, drive: DriveDep) -> dict[str, Any]:
    """Revoke a permission."""
    if not drive.remove_permission(file_id, permission_id):
        raise HTTPException(status_code=404, detail="Permission not found")
    return {"id": permission_id, "removed": True}
