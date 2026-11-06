"""Drive tools: search, read, upload and share files."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_drive import Drive, File
from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    WRITE,
    ToolDecorator,
    results,
)


def _file_text(drive: Drive, file: File) -> str:
    """Docs/Slides as text, Sheets as CSV, text files as they are; ToolError otherwise."""
    mime = file.mime_type
    if mime == "application/vnd.google-apps.spreadsheet":
        content = drive.export(file.id, "csv")
    elif mime.startswith("application/vnd.google-apps."):
        content = drive.export(file.id, "txt")
    elif mime.startswith("text/") or mime in ("application/json", "application/xml"):
        content = drive.get_content(file.id)
    else:
        raise ToolError(
            f"{file.name} is {mime}, not text. Download it with "
            f"`gsuite drive download {file.id}` instead."
        )
    return content.decode("utf-8", "replace")


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the drive tools on the server."""

    @tool(READ)
    def drive_search(
        name: str | None = None, query: str | None = None, max_results: int = 20
    ) -> dict[str, Any]:
        """Find files by name (contains) or with a raw Drive query
        (e.g. "mimeType = 'application/pdf' and modifiedTime > '2026-01-01'").
        """
        if name and not query:
            files = svc.drive.search(name)[:max_results]
        else:
            files = svc.drive.list_files(query=query, max_results=max_results)
        return results(to_json(files))

    @tool(READ)
    def drive_read_file(file_id: str, max_chars: int = 20000) -> dict[str, Any]:
        """Text of a file: Google Docs/Slides as text, Google Sheets as CSV, and
        plain-text files as they are. Binary files (PDF, images) are refused.
        """
        file = svc.drive.get(file_id)
        if file is None:
            raise ToolError(f"No file {file_id}")
        text = _file_text(svc.drive, file)
        return {
            "id": file.id,
            "name": file.name,
            "mime_type": file.mime_type,
            "truncated": len(text) > max_chars,
            "text": text[:max_chars],
        }

    @tool(WRITE)
    def drive_upload(
        path: str, parent_id: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Upload a local file (path on the machine running this server)."""
        return to_json(svc.drive.upload(path, name=name, parent_id=parent_id))  # type: ignore[no-any-return]

    @tool(WRITE)
    def drive_share(
        file_id: str,
        email: str | None = None,
        role: Literal["reader", "commenter", "writer"] = "reader",
        anyone: bool = False,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Share a file with a person (email) or with anyone who has the link
        (anyone=true). Confirm with the user first.
        """
        if not email and not anyone:
            raise ToolError("Give an email, or anyone=true for a link anyone can open")
        permission = svc.drive.add_permission(
            file_id,
            role=role,
            type="anyone" if anyone else "user",
            email=email,
            notify=notify,
        )
        return to_json(permission)  # type: ignore[no-any-return]
