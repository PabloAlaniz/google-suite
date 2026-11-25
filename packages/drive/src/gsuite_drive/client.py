"""Drive client - high-level interface."""

import io
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, BinaryIO

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

from gsuite_core import (
    GoogleAuth,
    execute,
    get_settings,
    map_http_error,
    paginate,
)
from gsuite_core.channels import Channel, channel_body, parse_channel, stop_body
from gsuite_core.exceptions import NotFoundError
from gsuite_core.service import GoogleService
from gsuite_drive._requests import (
    EXPORT_FORMATS,
    FILE_FIELDS,
    FOLDER_MIME_TYPE,
    PERMISSION_FIELDS,
    changes_params,
    default_export_format,
    export_mime_type,
    files_query,
    metadata_body,
    name_query,
    new_file_body,
    permission_request,
    split_changes,
)
from gsuite_drive.changes import ChangesDelta
from gsuite_drive.file import File, Folder
from gsuite_drive.parser import DriveParser
from gsuite_drive.permission import Permission

__all__ = [
    "EXPORT_FORMATS",
    "FILE_FIELDS",
    "FOLDER_MIME_TYPE",
    "PERMISSION_FIELDS",
    "Drive",
    "ProgressCallback",
    "default_export_format",
]

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float], None]


class Drive:
    """High-level Google Drive client.

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

    service = GoogleService("drive", "v3")

    def __init__(self, auth: GoogleAuth):
        """Initialize Drive client.

        Args:
            auth: GoogleAuth instance with valid credentials
        """
        self.auth = auth

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
        """Lazily yield files, following result pages.

        Args:
            query: Drive API query string (raw; quote values with drive_query_literal)
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to yield (None = all)
            order_by: Sort order
            trashed: False excludes trashed files, True lists only trashed
                files, None includes both
        """
        items = paginate(
            self.service.files().list,
            "files",
            "drive",
            max_items=max_results,
            page_size_param="pageSize",
            max_page_size=1000,
            q=files_query(query, parent_id, mime_type, trashed),
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
        """List files in Drive.

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
        """Search files by name.

        Args:
            name: File name to search
            exact: Exact match vs contains

        Returns:
            Matching files
        """
        return self.list_files(query=name_query(name, exact))

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
        """Download file content as bytes.

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
        """Export a Google Doc, Sheet, Slides or Drawing.

        Args:
            file_id: File ID
            format: Short name ("pdf", "docx", "xlsx", "csv", ...; see
                EXPORT_FORMATS) or a MIME type

        Returns:
            Exported content. Drive caps exports at 10 MB.
        """
        content: bytes = execute(
            self.service.files().export(fileId=file_id, mimeType=export_mime_type(format)),
            "drive",
            "file",
            file_id,
        )
        return content

    def download(self, file_id: str, path: str, export_format: str | None = None) -> str:
        """Download file to local path.

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
        Path(path).write_bytes(content)
        return path

    def update(
        self,
        file_id: str,
        name: str | None = None,
        description: str | None = None,
        starred: bool | None = None,
    ) -> File:
        """Update file metadata. Only the arguments you pass are changed.

        Returns:
            The updated File
        """
        updated = execute(
            self.service.files().update(
                fileId=file_id,
                body=metadata_body(name, description, starred),
                fields=FILE_FIELDS,
                supportsAllDrives=True,
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
        """Copy a file. Folders can't be copied.

        Args:
            file_id: File to copy
            name: Name of the copy (default: Drive's "Copy of ...")
            parent_id: Folder for the copy (default: same as the original)

        Returns:
            The new file
        """
        copied = execute(
            self.service.files().copy(
                fileId=file_id,
                body=new_file_body(name, parent_id),
                fields=FILE_FIELDS,
                supportsAllDrives=True,
            ),
            "drive",
            "file",
            file_id,
        )
        return self._parse_file(copied)

    def move(self, file_id: str, parent_id: str) -> File:
        """Move a file into another folder (removing it from its current ones).

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
        """Upload a file (resumable, in chunks; each chunk is retried on failure).

        Args:
            path: Local file path
            name: Name in Drive (default: local filename)
            parent_id: Parent folder ID
            mime_type: MIME type (auto-detected if not provided)
            on_progress: Called with the fraction uploaded (0.0-1.0)

        Returns:
            Created File
        """
        metadata = new_file_body(name or Path(path).name, parent_id)
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
        """Upload content directly.

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

        metadata = new_file_body(name, parent_id)
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
        """Create a folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Created Folder
        """
        metadata = new_file_body(name, parent_id, FOLDER_MIME_TYPE)
        created = execute(
            self.service.files().create(body=metadata, fields=FILE_FIELDS, supportsAllDrives=True),
            "drive",
            "folder",
        )
        return DriveParser.to_folder(self._parse_file(created))

    # ========== Delete/Trash ==========

    def trash(self, file_id: str) -> bool:
        """Move file to trash.

        Returns:
            True if trashed, False if the file doesn't exist. Other failures
            (auth, permissions, rate limit) raise.
        """
        return self._set_trashed(file_id, True)

    def restore(self, file_id: str) -> bool:
        """Restore a file from the trash.

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
            logger.warning("File not found for %s: %s", action, file_id)
            return False
        logger.info("%s file %s", "Trashed" if trashed else "Restored", file_id)
        return True

    def delete(self, file_id: str) -> bool:
        """Permanently delete file. Prefer trash() unless you mean it.

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
            logger.warning("File not found for deletion: %s", file_id)
            return False
        logger.info("Deleted file %s", file_id)
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
        """Grant access to a file.

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
        body, params = permission_request(role, type, email, domain, notify)
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
        logger.info("Granted %s on %s to %s", role, file_id, email or domain or type)
        return Permission.from_api(created)

    def share(
        self,
        file_id: str,
        email: str,
        role: str = "reader",
        notify: bool = True,
    ) -> bool:
        """Share a file with someone.

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
            logger.warning("File not found for sharing: %s", file_id)
            return False
        return True

    def remove_permission(self, file_id: str, permission_id: str) -> bool:
        """Revoke a permission.

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
        logger.info("Removed permission %s from %s", permission_id, file_id)
        return True

    # ========== Changes ==========

    def get_start_page_token(self) -> str:
        """The page token for "from now on": where a first ``changes`` call starts."""
        data = execute(
            self.service.changes().getStartPageToken(supportsAllDrives=True), "drive", "changes"
        )
        return str(data["startPageToken"])

    def changes(self, page_token: str) -> ChangesDelta:
        """Files changed or removed since ``page_token``, in My Drive and shared drives.

        Follows every page; keep ``delta.page_token`` for the next call.

        Args:
            page_token: From ``get_start_page_token()`` or the previous delta
        """
        params = changes_params(page_token)
        delta = ChangesDelta()
        while True:
            page = execute(self.service.changes().list(**params), "drive", "changes")
            changed, removed = split_changes(page)
            delta.changed += [self._parse_file(data) for data in changed]
            delta.removed += removed
            if not page.get("nextPageToken"):
                delta.page_token = page.get("newStartPageToken")
                return delta
            params["pageToken"] = page["nextPageToken"]

    def watch_changes(
        self,
        address: str,
        token: str,
        page_token: str | None = None,
        channel_id: str | None = None,
        ttl: int | None = None,
    ) -> Channel:
        """Have Google POST to ``address`` whenever a file the user can see changes.

        The notification has no body: call ``changes()`` with the page token
        you kept to get what changed. Google sends ``token`` back in
        ``X-Goog-Channel-Token``; check it, the notification isn't signed.
        Channels expire (``channel.expiration``, a day by default, a week at
        most) and aren't renewed: watch again before then.

        Args:
            address: HTTPS URL that receives the notifications
            token: Secret to verify them with
            page_token: Notify about changes after this token (default: from now)
            channel_id: Your ID for the channel (default: a random UUID)
            ttl: Seconds the channel should live (Google caps it)
        """
        body = channel_body(address, token, channel_id, ttl)
        data = execute(
            self.service.changes().watch(
                pageToken=page_token or self.get_start_page_token(),
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                body=body,
            ),
            "drive",
            "channel",
        )
        return parse_channel(data, token)

    def stop_channel(self, channel: Channel | str, resource_id: str | None = None) -> None:
        """Stop a notification channel.

        Args:
            channel: The Channel ``watch_changes`` returned, or its ID
            resource_id: The channel's ``resource_id``, when passing the ID
        """
        execute(
            self.service.channels().stop(body=stop_body(channel, resource_id)), "drive", "channel"
        )

    # ========== Parsing ==========

    def _parse_file(self, data: dict[str, Any]) -> File:
        """Parse Drive API response to File object."""
        file = DriveParser.parse_file(data)
        file._drive = self
        return file
