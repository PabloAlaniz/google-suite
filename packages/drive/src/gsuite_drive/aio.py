"""Async Drive: AsyncDrive, the async counterpart of ``Drive``.

Covers listing and search, metadata (get, update, rename, copy, move),
content (download, export), resumable uploads, folders, trash and delete, and
permissions, with the same arguments and results as the sync client.
Requests go through ``gsuite_core.aio``, so retries, rate limits and errors
are the suite's; query strings, bodies and parsing are the sync client's own
code.

Uploads are resumable and sent in chunks (8 MiB by default). A chunk that
fails (network error, 5xx, 429) is not resent blindly: the client asks Drive
how many bytes it has and resumes from there, so a retry can't corrupt or
duplicate the file. Downloads are read into memory, as in the sync client.

Files returned here are not linked to a sync client: their fluent methods
(``file.trash()``, ``file.download()``, ``folder.list_files()``) raise,
pointing to the AsyncDrive method to await instead.

Example:
    async with AsyncDrive(auth) as drive:
        for file in await drive.search("budget"):
            print(file.name)
        await drive.upload("report.pdf", parent_id=folder_id)

Requires ``pip install "gsuite-sdk[async]"``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import mimetypes
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, BinaryIO, NoReturn
from urllib.parse import quote

from gsuite_core import get_settings
from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.api_utils import _backoff
from gsuite_core.exceptions import APIError, NotFoundError, RateLimitError
from gsuite_drive._requests import (
    FILE_FIELDS,
    FOLDER_MIME_TYPE,
    PERMISSION_FIELDS,
    export_mime_type,
    files_query,
    metadata_body,
    name_query,
    new_file_body,
    permission_request,
)
from gsuite_drive.file import File, Folder
from gsuite_drive.parser import DriveParser
from gsuite_drive.permission import Permission

API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
# Drive wants chunks in multiples of 256 KiB (except the last one)
CHUNK_SIZE = 32 * 256 * 1024
RESUME_INCOMPLETE = 308
_ALL_DRIVES = {"supportsAllDrives": True}

ProgressCallback = Callable[[float], None]
Reader = Callable[[int, int], bytes]


class _AsyncOnly:
    """Stands in for the sync client on files from AsyncDrive.

    The fluent methods of File and Folder call the sync client; without this,
    trash() and delete() would silently do nothing.
    """

    def __getattr__(self, name: str) -> NoReturn:
        raise TypeError(
            "This file came from AsyncDrive, whose files have no sync client: "
            "await drive.download(...), drive.trash(...), drive.list_files(parent_id=...) "
            "instead"
        )


_ASYNC_ONLY: Any = _AsyncOnly()


def _segment(value: str) -> str:
    return quote(value, safe="")


def _resume_offset(range_header: str | None) -> int:
    """Next byte to send after a 308: ``Range: bytes=0-N`` means 0..N arrived."""
    if not range_header:
        return 0
    return int(range_header.rsplit("-", 1)[1]) + 1


def _retryable(exc: BaseException) -> bool:
    """A failed chunk worth resuming: rate limit, 5xx, or a network error."""
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIError):
        return (exc.status_code or 0) >= 500  # noqa: PLR2004 - server errors
    # httpx is optional (the [async] extra), so match its network errors by class
    return any(cls.__name__ == "TransportError" for cls in type(exc).__mro__)


async def _reader(content: bytes | BinaryIO) -> tuple[Reader, int]:
    """(read(offset, size), total size) for bytes or a file object."""
    if not isinstance(content, bytes) and content.seekable():
        stream, start = content, content.tell()
        total = await asyncio.to_thread(stream.seek, 0, os.SEEK_END) - start

        def read_stream(offset: int, size: int) -> bytes:
            stream.seek(start + offset)
            return stream.read(size)

        return read_stream, total

    data = content if isinstance(content, bytes) else await asyncio.to_thread(content.read)

    def read_bytes(offset: int, size: int) -> bytes:
        return data[offset : offset + size]

    return read_bytes, len(data)


class AsyncDrive:
    """Async Drive client (My Drive and shared drives).

    Args:
        auth: GoogleAuth (OAuth or service account) or google-auth credentials
        chunk_size: Upload chunk size in bytes (a multiple of 256 KiB)
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT)
        transport: httpx transport (tests)
    """

    def __init__(
        self,
        auth: Any,
        *,
        chunk_size: int = CHUNK_SIZE,
        timeout: float | None = None,
        transport: Any = None,
    ) -> None:
        if chunk_size <= 0 or chunk_size % (256 * 1024):
            raise ValueError("chunk_size must be a positive multiple of 256 KiB")
        self._http = AsyncGoogleClient(auth, timeout=timeout, transport=transport)
        self.chunk_size = chunk_size

    async def __aenter__(self) -> AsyncDrive:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    # ---- plumbing ----

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        kwargs.setdefault("service", "drive")
        return await self._http.json(method, f"{API}/{path}", **kwargs)

    @staticmethod
    def _link(file: File) -> File:
        return dataclasses.replace(file, _drive=_ASYNC_ONLY)

    def _parse(self, data: dict[str, Any]) -> File:
        return self._link(DriveParser.parse_file(data))

    def _parse_folder(self, data: dict[str, Any]) -> Folder:
        return DriveParser.to_folder(self._parse(data))

    # ---- listing ----

    async def iter_files(
        self,
        query: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        max_results: int | None = 100,
        order_by: str = "modifiedTime desc",
        trashed: bool | None = False,
    ) -> AsyncIterator[File]:
        """Lazily yield files, following result pages (same filters as ``Drive.iter_files``)."""
        async for data in self._http.paginate(
            f"{API}/files",
            "files",
            service="drive",
            params={
                "q": files_query(query, parent_id, mime_type, trashed),
                "orderBy": order_by,
                # nextPageToken must be requested explicitly when fields is set
                "fields": f"nextPageToken, files({FILE_FIELDS})",
                "includeItemsFromAllDrives": True,
                **_ALL_DRIVES,
            },
            max_items=max_results,
            page_size_param="pageSize",
            max_page_size=1000,
        ):
            yield self._parse(data)

    async def list_files(
        self,
        query: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        max_results: int | None = 100,
        order_by: str = "modifiedTime desc",
        trashed: bool | None = False,
    ) -> list[File]:
        """Files matching the filters (None = all)."""
        return [
            file
            async for file in self.iter_files(
                query, parent_id, mime_type, max_results, order_by, trashed
            )
        ]

    async def list_folders(self, parent_id: str | None = None) -> list[Folder]:
        """Folders, optionally inside ``parent_id``."""
        files = self.iter_files(parent_id=parent_id, mime_type=FOLDER_MIME_TYPE)
        return [DriveParser.to_folder(file) async for file in files]

    async def search(self, name: str, exact: bool = False) -> list[File]:
        """Files whose name contains (or equals) ``name``."""
        return await self.list_files(query=name_query(name, exact))

    # ---- files ----

    async def get(self, file_id: str) -> File | None:
        """A file by ID, or None if it doesn't exist."""
        try:
            data = await self._json(
                "GET",
                f"files/{_segment(file_id)}",
                params={"fields": FILE_FIELDS, **_ALL_DRIVES},
                resource_type="file",
                resource_id=file_id,
            )
        except NotFoundError:
            return None
        return self._parse(data)

    async def get_content(self, file_id: str) -> bytes:
        """A file's bytes. Google Docs/Sheets/Slides have none; use export()."""
        response = await self._http.request(
            "GET",
            f"{API}/files/{_segment(file_id)}",
            service="drive",
            params={"alt": "media", **_ALL_DRIVES},
            resource_type="file",
            resource_id=file_id,
        )
        content: bytes = response.content
        return content

    async def export(self, file_id: str, format: str) -> bytes:
        """Export a Google file ("pdf", "docx", "csv", ... or a MIME type); 10 MB cap."""
        response = await self._http.request(
            "GET",
            f"{API}/files/{_segment(file_id)}/export",
            service="drive",
            params={"mimeType": export_mime_type(format)},
            resource_type="file",
            resource_id=file_id,
        )
        content: bytes = response.content
        return content

    async def download(self, file_id: str, path: str, export_format: str | None = None) -> str:
        """Save a file (or an export of a Google file) to ``path``; returns the path."""
        if export_format:
            content = await self.export(file_id, export_format)
        else:
            content = await self.get_content(file_id)
        await asyncio.to_thread(Path(path).write_bytes, content)
        return path

    async def update(
        self,
        file_id: str,
        name: str | None = None,
        description: str | None = None,
        starred: bool | None = None,
    ) -> File:
        """Change metadata; only the arguments you pass are changed."""
        data = await self._json(
            "PATCH",
            f"files/{_segment(file_id)}",
            params={"fields": FILE_FIELDS, **_ALL_DRIVES},
            json=metadata_body(name, description, starred),
            resource_type="file",
            resource_id=file_id,
        )
        return self._parse(data)

    async def rename(self, file_id: str, name: str) -> File:
        """Rename a file."""
        return await self.update(file_id, name=name)

    async def copy(
        self, file_id: str, name: str | None = None, parent_id: str | None = None
    ) -> File:
        """Copy a file (not a folder); returns the copy."""
        data = await self._json(
            "POST",
            f"files/{_segment(file_id)}/copy",
            params={"fields": FILE_FIELDS, **_ALL_DRIVES},
            json=new_file_body(name, parent_id),
            resource_type="file",
            resource_id=file_id,
        )
        return self._parse(data)

    async def move(self, file_id: str, parent_id: str) -> File:
        """Move a file into a folder, out of its current ones."""
        current = await self._json(
            "GET",
            f"files/{_segment(file_id)}",
            params={"fields": "parents", **_ALL_DRIVES},
            resource_type="file",
            resource_id=file_id,
        )
        data = await self._json(
            "PATCH",
            f"files/{_segment(file_id)}",
            params={
                "addParents": parent_id,
                "removeParents": ",".join(current.get("parents", [])),
                "fields": FILE_FIELDS,
                **_ALL_DRIVES,
            },
            json={},
            resource_type="file",
            resource_id=file_id,
        )
        return self._parse(data)

    async def create_folder(self, name: str, parent_id: str | None = None) -> Folder:
        """Create a folder."""
        data = await self._json(
            "POST",
            "files",
            params={"fields": FILE_FIELDS, **_ALL_DRIVES},
            json=new_file_body(name, parent_id, FOLDER_MIME_TYPE),
            resource_type="folder",
        )
        return self._parse_folder(data)

    async def trash(self, file_id: str) -> bool:
        """Move to the trash; False if the file doesn't exist."""
        return await self._set_trashed(file_id, True)

    async def restore(self, file_id: str) -> bool:
        """Take out of the trash; False if the file doesn't exist."""
        return await self._set_trashed(file_id, False)

    async def _set_trashed(self, file_id: str, trashed: bool) -> bool:
        try:
            await self._json(
                "PATCH",
                f"files/{_segment(file_id)}",
                params=_ALL_DRIVES,
                json={"trashed": trashed},
                resource_type="file",
                resource_id=file_id,
            )
        except NotFoundError:
            return False
        return True

    async def delete(self, file_id: str) -> bool:
        """Delete for good (prefer trash()); False if the file doesn't exist."""
        try:
            await self._json(
                "DELETE",
                f"files/{_segment(file_id)}",
                params=_ALL_DRIVES,
                resource_type="file",
                resource_id=file_id,
            )
        except NotFoundError:
            return False
        return True

    # ---- uploads ----

    async def upload(
        self,
        path: str,
        name: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> File:
        """Upload a local file (resumable, in chunks); returns the new file."""
        source = Path(path)
        total = (await asyncio.to_thread(source.stat)).st_size

        def read(offset: int, size: int) -> bytes:
            with source.open("rb") as f:
                f.seek(offset)
                return f.read(size)

        guessed = mime_type or mimetypes.guess_type(source.name)[0]
        return await self._upload(
            new_file_body(name or source.name, parent_id),
            read,
            total,
            guessed or "application/octet-stream",
            on_progress,
        )

    async def upload_content(
        self,
        content: bytes | BinaryIO,
        name: str,
        parent_id: str | None = None,
        mime_type: str = "application/octet-stream",
        on_progress: ProgressCallback | None = None,
    ) -> File:
        """Upload bytes or a file object (resumable, in chunks); returns the new file.

        A seekable file object is read chunk by chunk from its current position;
        any other is read whole first.
        """
        read, total = await _reader(content)
        return await self._upload(
            new_file_body(name, parent_id), read, total, mime_type, on_progress
        )

    async def _upload(
        self,
        metadata: dict[str, Any],
        read: Reader,
        total: int,
        mime_type: str,
        on_progress: ProgressCallback | None,
    ) -> File:
        session = await self._http.request(
            "POST",
            UPLOAD_API,
            service="drive",
            resource_type="file",
            params={"uploadType": "resumable", "fields": FILE_FIELDS, **_ALL_DRIVES},
            json=metadata,
            headers={"X-Upload-Content-Type": mime_type, "X-Upload-Content-Length": str(total)},
        )
        response = await self._send_chunks(session.headers["location"], read, total, on_progress)
        if on_progress:
            on_progress(1.0)
        return self._parse(response.json())

    async def _send_chunks(
        self, url: str, read: Reader, total: int, on_progress: ProgressCallback | None
    ) -> Any:
        """PUT the content chunk by chunk; returns the final (200/201) response."""
        settings = get_settings()
        offset, failures, probe = 0, 0, False
        while True:
            chunk = b"" if probe else await asyncio.to_thread(read, offset, self.chunk_size)
            if chunk:
                content_range = f"bytes {offset}-{offset + len(chunk) - 1}/{total}"
            else:  # a status query, or an empty file
                content_range = f"bytes */{total}"
            try:
                response = await self._http.request(
                    "PUT",
                    url,
                    service="drive",
                    resource_type="file",
                    content=chunk,
                    headers={"Content-Range": content_range},
                    accept=(RESUME_INCOMPLETE,),
                    retry=False,
                )
            except Exception as exc:
                if not _retryable(exc) or failures >= settings.max_retries:
                    raise
                await asyncio.sleep(_backoff(failures, settings.retry_delay))
                failures += 1
                probe = True  # ask Drive what it has before sending more
                continue
            if response.status_code != RESUME_INCOMPLETE:
                return response
            offset, failures, probe = _resume_offset(response.headers.get("range")), 0, False
            if on_progress and total:
                on_progress(offset / total)

    # ---- permissions ----

    async def list_permissions(self, file_id: str) -> list[Permission]:
        """Who has access to a file."""
        return [
            Permission.from_api(data)
            async for data in self._http.paginate(
                f"{API}/files/{_segment(file_id)}/permissions",
                "permissions",
                service="drive",
                params={
                    "fields": f"nextPageToken, permissions({PERMISSION_FIELDS})",
                    **_ALL_DRIVES,
                },
                page_size_param="pageSize",
                max_page_size=100,
            )
        ]

    async def add_permission(
        self,
        file_id: str,
        role: str = "reader",
        type: str = "user",
        email: str | None = None,
        domain: str | None = None,
        notify: bool = True,
    ) -> Permission:
        """Grant access (same rules as ``Drive.add_permission``)."""
        body, params = permission_request(role, type, email, domain, notify)
        data = await self._json(
            "POST",
            f"files/{_segment(file_id)}/permissions",
            params={"fields": PERMISSION_FIELDS, **_ALL_DRIVES, **params},
            json=body,
            resource_type="file",
            resource_id=file_id,
        )
        return Permission.from_api(data)

    async def share(
        self, file_id: str, email: str, role: str = "reader", notify: bool = True
    ) -> bool:
        """Share with a person; False if the file doesn't exist."""
        try:
            await self.add_permission(file_id, role=role, type="user", email=email, notify=notify)
        except NotFoundError:
            return False
        return True

    async def remove_permission(self, file_id: str, permission_id: str) -> bool:
        """Revoke a permission; False if the file or permission doesn't exist."""
        try:
            await self._json(
                "DELETE",
                f"files/{_segment(file_id)}/permissions/{_segment(permission_id)}",
                params=_ALL_DRIVES,
                resource_type="permission",
                resource_id=permission_id,
            )
        except NotFoundError:
            return False
        return True
