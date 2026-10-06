"""Drive client - high-level interface."""

import io
import logging
import os
from collections.abc import Callable, Iterator
from typing import Any, BinaryIO

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

from gsuite_core import (
    GoogleAuth,
    authorized_http,
    drive_query_literal,
    execute,
    get_settings,
    map_http_error,
    paginate,
)
from gsuite_core.exceptions import NotFoundError, ValidationError
from gsuite_drive.file import File, Folder
from gsuite_drive.parser import DriveParser
from gsuite_drive.permission import Permission

logger = logging.getLogger(__name__)

FILE_FIELDS = (
    "id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, "
    "webContentLink, description, starred, trashed, md5Checksum"
)
PERMISSION_FIELDS = "id, type, role, emailAddress, domain, displayName"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

# Short names accepted by export(); values are the MIME types Drive exports to.
EXPORT_FORMATS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "md": "text/markdown",
    "html": "text/html",
    "epub": "application/epub+zip",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
}

_DEFAULT_EXPORTS = {
    "application/vnd.google-apps.document": "docx",
    "application/vnd.google-apps.spreadsheet": "xlsx",
    "application/vnd.google-apps.presentation": "pptx",
    "application/vnd.google-apps.drawing": "pdf",
}

ProgressCallback = Callable[[float], None]


def default_export_format(mime_type: str) -> str:
    """Export format used when downloading a Google file without choosing one."""
    return _DEFAULT_EXPORTS.get(mime_type, "pdf")


class Drive:
    """
    High-level Google Drive client.

    Works with My Drive and shared drives.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        drive = Drive(auth)

        # List files
        for file in drive.list_files():
            print(f"{file.name} ({file.mime_type})")

        # Upload
        drive.upload("document.pdf")

        # Download (Google Docs are exported)
        file = drive.get("file_id")
        file.download("local_copy.pdf")
    """

    def __init__(self, auth: GoogleAuth):
        """
        Initialize Drive client.

        Args:
            auth: GoogleAuth instance with valid credentials
        """
        self.auth = auth
        self._service: Any = None

    @property
    def service(self) -> Any:
        """Lazy-load Drive API service."""
        if self._service is None:
            self._service = build(
                "drive", "v3", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._service

    # ========== File listing ==========

    def iter_files(
        self,
        query: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        max_results: int | None = 100,
        order_by: str = "modifiedTime desc",
        trashed: bool | None = False,
    ) -> Iterator[File]:
        """
        Lazily yield files, following result pages.

        Args:
            query: Drive API query string (raw; quote values with drive_query_literal)
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to yield (None = all)
            order_by: Sort order
            trashed: False excludes trashed files, True lists only trashed
                files, None includes both
        """
        query_parts = []
        if query:
            query_parts.append(f"({query})")
        if parent_id:
            query_parts.append(f"{drive_query_literal(parent_id)} in parents")
        if mime_type:
            query_parts.append(f"mimeType={drive_query_literal(mime_type)}")
        if trashed is not None:
            query_parts.append(f"trashed={'true' if trashed else 'false'}")

        items = paginate(
            self.service.files().list,
            "files",
            "drive",
            max_items=max_results,
            page_size_param="pageSize",
            max_page_size=1000,
            q=" and ".join(query_parts),
            orderBy=order_by,
            # nextPageToken must be requested explicitly when fields is set
            fields=f"nextPageToken, files({FILE_FIELDS})",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        for item in items:
            yield self._parse_file(item)

    def list_files(
        self,
        query: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        max_results: int | None = 100,
        order_by: str = "modifiedTime desc",
        trashed: bool | None = False,
    ) -> list[File]:
        """
        List files in Drive.

        Args:
            query: Drive API query string (raw; quote values with drive_query_literal)
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to return (None = all)
            order_by: Sort order
            trashed: False excludes trashed files, True lists only trashed
                files, None includes both

        Returns:
            List of File objects
        """
        return list(self.iter_files(query, parent_id, mime_type, max_results, order_by, trashed))

    def list_folders(self, parent_id: str | None = None) -> list[Folder]:
        """List folders."""
        files = self.iter_files(parent_id=parent_id, mime_type=FOLDER_MIME_TYPE)
        return [DriveParser.to_folder(f) for f in files]

    def search(self, name: str, exact: bool = False) -> list[File]:
        """
        Search files by name.

        Args:
            name: File name to search
            exact: Exact match vs contains

        Returns:
            Matching files
        """
        literal = drive_query_literal(name)
        query = f"name={literal}" if exact else f"name contains {literal}"

        return self.list_files(query=query)

    # ========== File operations ==========

    def get(self, file_id: str) -> File | None:
        """Get a file by ID, or None if it doesn't exist."""
        try:
            item = execute(
                self.service.files().get(
                    fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True
                ),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            return None
        return self._parse_file(item)

    def get_content(self, file_id: str) -> bytes:
        """
        Download file content as bytes.

        Google Docs/Sheets/Slides have no binary content; use export().
        """
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        try:
            while not done:
                # Chunks retry 5xx/429 themselves; downloads are idempotent
                _, done = downloader.next_chunk(num_retries=get_settings().max_retries)
        except HttpError as e:
            raise map_http_error(e, "drive", "file", file_id) from e

        return buffer.getvalue()

    def export(self, file_id: str, format: str) -> bytes:
        """
        Export a Google Doc, Sheet, Slides or Drawing.

        Args:
            file_id: File ID
            format: Short name ("pdf", "docx", "xlsx", "csv", ...; see
                EXPORT_FORMATS) or a MIME type

        Returns:
            Exported content. Drive caps exports at 10 MB.
        """
        mime_type = EXPORT_FORMATS.get(format.lower(), format)
        if "/" not in mime_type:
            raise ValidationError(
                "format", f"unknown export format {format!r}; use one of {sorted(EXPORT_FORMATS)}"
            )
        content: bytes = execute(
            self.service.files().export(fileId=file_id, mimeType=mime_type),
            "drive",
            "file",
            file_id,
        )
        return content

    def download(self, file_id: str, path: str, export_format: str | None = None) -> str:
        """
        Download file to local path.

        Args:
            file_id: File ID
            path: Local path to save
            export_format: Export Google files to this format instead of
                downloading (required for Docs/Sheets/Slides)

        Returns:
            Path where file was saved
        """
        if export_format:
            content = self.export(file_id, export_format)
        else:
            content = self.get_content(file_id)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def update(
        self,
        file_id: str,
        name: str | None = None,
        description: str | None = None,
        starred: bool | None = None,
    ) -> File:
        """
        Update file metadata. Only the arguments you pass are changed.

        Returns:
            The updated File
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if starred is not None:
            body["starred"] = starred

        updated = execute(
            self.service.files().update(
                fileId=file_id, body=body, fields=FILE_FIELDS, supportsAllDrives=True
            ),
            "drive",
            "file",
            file_id,
        )
        return self._parse_file(updated)

    def rename(self, file_id: str, name: str) -> File:
        """Rename a file."""
        return self.update(file_id, name=name)

    def copy(self, file_id: str, name: str | None = None, parent_id: str | None = None) -> File:
        """
        Copy a file. Folders can't be copied.

        Args:
            file_id: File to copy
            name: Name of the copy (default: Drive's "Copy of ...")
            parent_id: Folder for the copy (default: same as the original)

        Returns:
            The new file
        """
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if parent_id:
            body["parents"] = [parent_id]

        copied = execute(
            self.service.files().copy(
                fileId=file_id, body=body, fields=FILE_FIELDS, supportsAllDrives=True
            ),
            "drive",
            "file",
            file_id,
        )
        return self._parse_file(copied)

    def move(self, file_id: str, parent_id: str) -> File:
        """
        Move a file into another folder (removing it from its current ones).

        Returns:
            The moved file
        """
        current = execute(
            self.service.files().get(fileId=file_id, fields="parents", supportsAllDrives=True),
            "drive",
            "file",
            file_id,
        )
        moved = execute(
            self.service.files().update(
                fileId=file_id,
                addParents=parent_id,
                removeParents=",".join(current.get("parents", [])),
                fields=FILE_FIELDS,
                supportsAllDrives=True,
            ),
            "drive",
            "file",
            file_id,
        )
        return self._parse_file(moved)

    # ========== Upload ==========

    def upload(
        self,
        path: str,
        name: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> File:
        """
        Upload a file (resumable, in chunks; each chunk is retried on failure).

        Args:
            path: Local file path
            name: Name in Drive (default: local filename)
            parent_id: Parent folder ID
            mime_type: MIME type (auto-detected if not provided)
            on_progress: Called with the fraction uploaded (0.0-1.0)

        Returns:
            Created File
        """
        metadata: dict[str, Any] = {"name": name or os.path.basename(path)}
        if parent_id:
            metadata["parents"] = [parent_id]

        media = MediaFileUpload(path, mimetype=mime_type, resumable=True)
        return self._upload(metadata, media, on_progress)

    def upload_content(
        self,
        content: bytes | BinaryIO,
        name: str,
        parent_id: str | None = None,
        mime_type: str = "application/octet-stream",
        on_progress: ProgressCallback | None = None,
    ) -> File:
        """
        Upload content directly.

        Args:
            content: File content as bytes or file-like object
            name: Name in Drive
            parent_id: Parent folder ID
            mime_type: MIME type
            on_progress: Called with the fraction uploaded (0.0-1.0)

        Returns:
            Created File
        """
        buffer = io.BytesIO(content) if isinstance(content, bytes) else content

        metadata: dict[str, Any] = {"name": name}
        if parent_id:
            metadata["parents"] = [parent_id]

        media = MediaIoBaseUpload(buffer, mimetype=mime_type, resumable=True)
        return self._upload(metadata, media, on_progress)

    def _upload(
        self, metadata: dict[str, Any], media: Any, on_progress: ProgressCallback | None
    ) -> File:
        request = self.service.files().create(
            body=metadata, media_body=media, fields=FILE_FIELDS, supportsAllDrives=True
        )
        response = None
        try:
            while response is None:
                # Resumable uploads continue from the last acknowledged byte,
                # so retrying a chunk can't duplicate the file.
                status, response = request.next_chunk(num_retries=get_settings().max_retries)
                if status and on_progress:
                    on_progress(status.progress())
        except HttpError as e:
            raise map_http_error(e, "drive", "file") from e

        if on_progress:
            on_progress(1.0)
        return self._parse_file(response)

    # ========== Folder operations ==========

    def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
    ) -> Folder:
        """
        Create a folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Created Folder
        """
        metadata: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME_TYPE}
        if parent_id:
            metadata["parents"] = [parent_id]

        created = execute(
            self.service.files().create(body=metadata, fields=FILE_FIELDS, supportsAllDrives=True),
            "drive",
            "folder",
        )
        return DriveParser.to_folder(self._parse_file(created))

    # ========== Delete/Trash ==========

    def trash(self, file_id: str) -> bool:
        """
        Move file to trash.

        Returns:
            True if trashed, False if the file doesn't exist. Other failures
            (auth, permissions, rate limit) raise.
        """
        return self._set_trashed(file_id, True)

    def restore(self, file_id: str) -> bool:
        """
        Restore a file from the trash.

        Returns:
            True if restored, False if the file doesn't exist. Other failures raise.
        """
        return self._set_trashed(file_id, False)

    def _set_trashed(self, file_id: str, trashed: bool) -> bool:
        action = "trash" if trashed else "restore"
        try:
            execute(
                self.service.files().update(
                    fileId=file_id, body={"trashed": trashed}, supportsAllDrives=True
                ),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            logger.warning(f"File not found for {action}: {file_id}")
            return False
        logger.info(f"{'Trashed' if trashed else 'Restored'} file {file_id}")
        return True

    def delete(self, file_id: str) -> bool:
        """
        Permanently delete file. Prefer trash() unless you mean it.

        Returns:
            True if deleted, False if the file doesn't exist. Other failures raise.
        """
        try:
            execute(
                self.service.files().delete(fileId=file_id, supportsAllDrives=True),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            logger.warning(f"File not found for deletion: {file_id}")
            return False
        logger.info(f"Deleted file {file_id}")
        return True

    # ========== Sharing ==========

    def list_permissions(self, file_id: str) -> list[Permission]:
        """List who has access to a file."""
        items = paginate(
            self.service.permissions().list,
            "permissions",
            "drive",
            page_size_param="pageSize",
            max_page_size=100,
            fileId=file_id,
            fields=f"nextPageToken, permissions({PERMISSION_FIELDS})",
            supportsAllDrives=True,
        )
        return [Permission.from_api(p) for p in items]

    def add_permission(
        self,
        file_id: str,
        role: str = "reader",
        type: str = "user",
        email: str | None = None,
        domain: str | None = None,
        notify: bool = True,
    ) -> Permission:
        """
        Grant access to a file.

        Args:
            file_id: File ID
            role: reader, commenter, writer, ...
            type: user, group, domain or anyone
            email: Required for user and group
            domain: Required for domain
            notify: Email the user or group (ignored for domain/anyone)

        Returns:
            The created Permission
        """
        if type in ("user", "group") and not email:
            raise ValidationError("email", f"required for type={type!r}")
        if type == "domain" and not domain:
            raise ValidationError("domain", "required for type='domain'")

        body: dict[str, Any] = {"type": type, "role": role}
        if email:
            body["emailAddress"] = email
        if domain:
            body["domain"] = domain

        params: dict[str, Any] = {}
        if type in ("user", "group"):
            params["sendNotificationEmail"] = notify

        created = execute(
            self.service.permissions().create(
                fileId=file_id,
                body=body,
                fields=PERMISSION_FIELDS,
                supportsAllDrives=True,
                **params,
            ),
            "drive",
            "file",
            file_id,
        )
        logger.info(f"Granted {role} on {file_id} to {email or domain or type}")
        return Permission.from_api(created)

    def share(
        self,
        file_id: str,
        email: str,
        role: str = "reader",
        notify: bool = True,
    ) -> bool:
        """
        Share a file with someone.

        Args:
            file_id: File ID
            email: Email to share with
            role: Permission role (reader, writer, commenter)
            notify: Send notification email

        Returns:
            True if shared, False if the file doesn't exist. Other failures
            (invalid role or email, permissions) raise.
        """
        try:
            self.add_permission(file_id, role=role, type="user", email=email, notify=notify)
        except NotFoundError:
            logger.error(f"File not found for sharing: {file_id}")
            return False
        return True

    def remove_permission(self, file_id: str, permission_id: str) -> bool:
        """
        Revoke a permission.

        Returns:
            True if removed, False if the file or permission doesn't exist.
        """
        try:
            execute(
                self.service.permissions().delete(
                    fileId=file_id, permissionId=permission_id, supportsAllDrives=True
                ),
                "drive",
                "permission",
                permission_id,
            )
        except NotFoundError:
            return False
        logger.info(f"Removed permission {permission_id} from {file_id}")
        return True

    # ========== Parsing ==========

    def _parse_file(self, data: dict) -> File:
        """Parse Drive API response to File object."""
        file = DriveParser.parse_file(data)
        file._drive = self
        return file
