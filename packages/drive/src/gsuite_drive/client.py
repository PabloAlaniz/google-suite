"""Drive client - high-level interface."""

import io
import logging
from collections.abc import Iterator
from typing import BinaryIO

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
from gsuite_core.exceptions import NotFoundError
from gsuite_drive.file import File, Folder
from gsuite_drive.parser import DriveParser

logger = logging.getLogger(__name__)

FILE_FIELDS = (
    "id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, webContentLink"
)


class Drive:
    """
    High-level Google Drive client.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        drive = Drive(auth)

        # List files
        for file in drive.list_files():
            print(f"{file.name} ({file.mime_type})")

        # Upload
        drive.upload("document.pdf")

        # Download
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
        self._service = None

    @property
    def service(self):
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
    ) -> Iterator[File]:
        """
        Lazily yield files, following result pages.

        Args:
            query: Drive API query string (raw; quote values with drive_query_literal)
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to yield (None = all)
            order_by: Sort order
        """
        query_parts = []
        if query:
            query_parts.append(f"({query})")
        if parent_id:
            query_parts.append(f"{drive_query_literal(parent_id)} in parents")
        if mime_type:
            query_parts.append(f"mimeType={drive_query_literal(mime_type)}")
        query_parts.append("trashed=false")

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
    ) -> list[File]:
        """
        List files in Drive.

        Args:
            query: Drive API query string (raw; quote values with drive_query_literal)
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to return (None = all)
            order_by: Sort order

        Returns:
            List of File objects
        """
        return list(self.iter_files(query, parent_id, mime_type, max_results, order_by))

    def list_folders(self, parent_id: str | None = None) -> list[Folder]:
        """List folders."""
        files = self.list_files(
            parent_id=parent_id,
            mime_type="application/vnd.google-apps.folder",
        )
        return [
            Folder(**{k: v for k, v in f.__dict__.items() if not k.startswith("_")}) for f in files
        ]

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
                self.service.files().get(fileId=file_id, fields=FILE_FIELDS),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            return None
        return self._parse_file(item)

    def get_content(self, file_id: str) -> bytes:
        """Download file content as bytes."""
        request = self.service.files().get_media(fileId=file_id)
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

    def download(self, file_id: str, path: str) -> str:
        """
        Download file to local path.

        Args:
            file_id: File ID
            path: Local path to save

        Returns:
            Path where file was saved
        """
        content = self.get_content(file_id)
        with open(path, "wb") as f:
            f.write(content)
        return path

    # ========== Upload ==========

    def upload(
        self,
        path: str,
        name: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
    ) -> File:
        """
        Upload a file.

        Args:
            path: Local file path
            name: Name in Drive (default: local filename)
            parent_id: Parent folder ID
            mime_type: MIME type (auto-detected if not provided)

        Returns:
            Created File
        """
        import os

        file_name = name or os.path.basename(path)

        metadata = {"name": file_name}
        if parent_id:
            metadata["parents"] = [parent_id]

        media = MediaFileUpload(path, mimetype=mime_type, resumable=True)

        created = execute(
            self.service.files().create(body=metadata, media_body=media, fields=FILE_FIELDS),
            "drive",
            "file",
        )

        return self._parse_file(created)

    def upload_content(
        self,
        content: bytes | BinaryIO,
        name: str,
        parent_id: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> File:
        """
        Upload content directly.

        Args:
            content: File content as bytes or file-like object
            name: Name in Drive
            parent_id: Parent folder ID
            mime_type: MIME type

        Returns:
            Created File
        """
        if isinstance(content, bytes):
            buffer = io.BytesIO(content)
        else:
            buffer = content

        metadata = {"name": name}
        if parent_id:
            metadata["parents"] = [parent_id]

        media = MediaIoBaseUpload(buffer, mimetype=mime_type, resumable=True)

        created = execute(
            self.service.files().create(body=metadata, media_body=media, fields=FILE_FIELDS),
            "drive",
            "file",
        )

        return self._parse_file(created)

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
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        created = execute(
            self.service.files().create(body=metadata, fields=FILE_FIELDS), "drive", "folder"
        )

        file = self._parse_file(created)
        return Folder(**{k: v for k, v in file.__dict__.items() if not k.startswith("_")})

    # ========== Delete/Trash ==========

    def trash(self, file_id: str) -> bool:
        """
        Move file to trash.

        Returns:
            True if trashed, False if the file doesn't exist. Other failures
            (auth, permissions, rate limit) raise.
        """
        try:
            execute(
                self.service.files().update(fileId=file_id, body={"trashed": True}),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            logger.warning(f"File not found for trash: {file_id}")
            return False
        logger.info(f"Trashed file {file_id}")
        return True

    def delete(self, file_id: str) -> bool:
        """
        Permanently delete file.

        Returns:
            True if deleted, False if the file doesn't exist. Other failures raise.
        """
        try:
            execute(self.service.files().delete(fileId=file_id), "drive", "file", file_id)
        except NotFoundError:
            logger.warning(f"File not found for deletion: {file_id}")
            return False
        logger.info(f"Deleted file {file_id}")
        return True

    # ========== Sharing ==========

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
            execute(
                self.service.permissions().create(
                    fileId=file_id,
                    body={"type": "user", "role": role, "emailAddress": email},
                    sendNotificationEmail=notify,
                ),
                "drive",
                "file",
                file_id,
            )
        except NotFoundError:
            logger.error(f"File not found for sharing: {file_id}")
            return False
        logger.info(f"Shared file {file_id} with {email} ({role})")
        return True

    # ========== Parsing ==========

    def _parse_file(self, data: dict) -> File:
        """Parse Drive API response to File object."""
        file = DriveParser.parse_file(data)
        file._drive = self
        return file
