"""Drive client - high-level interface."""

import io
import logging
from typing import BinaryIO

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

from gsuite_core import GoogleAuth
from gsuite_drive.file import File, Folder
from gsuite_drive.parser import DriveParser

logger = logging.getLogger(__name__)


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
            self._service = build("drive", "v3", credentials=self.auth.credentials)
        return self._service

    # ========== File listing ==========

    def list_files(
        self,
        query: str | None = None,
        parent_id: str | None = None,
        mime_type: str | None = None,
        max_results: int = 100,
        order_by: str = "modifiedTime desc",
    ) -> list[File]:
        """
        List files in Drive.

        Args:
            query: Drive API query string
            parent_id: Filter by parent folder ID
            mime_type: Filter by MIME type
            max_results: Maximum files to return
            order_by: Sort order

        Returns:
            List of File objects
        """
        # Build query
        query_parts = []
        if query:
            query_parts.append(query)
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        if mime_type:
            query_parts.append(f"mimeType='{mime_type}'")

        # Don't include trashed files
        query_parts.append("trashed=false")

        full_query = " and ".join(query_parts)

        response = (
            self.service.files()
            .list(
                q=full_query,
                pageSize=min(max_results, 1000),
                orderBy=order_by,
                fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, webContentLink)",
            )
            .execute()
        )

        files = []
        for item in response.get("files", []):
            file = self._parse_file(item)
            files.append(file)

        return files

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
        if exact:
            query = f"name='{name}'"
        else:
            query = f"name contains '{name}'"

        return self.list_files(query=query)

    # ========== File operations ==========

    def get(self, file_id: str) -> File | None:
        """Get a file by ID."""
        try:
            item = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink, webContentLink",
                )
                .execute()
            )
            return self._parse_file(item)
        except HttpError as e:
            if e.resp.status == 404:
                logger.debug(f"File not found: {file_id}")
                return None
            logger.error(f"Error getting file {file_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting file {file_id}: {e}")
            return None

    def get_content(self, file_id: str) -> bytes:
        """Download file content as bytes."""
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

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

        created = (
            self.service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink",
            )
            .execute()
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

        created = (
            self.service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink",
            )
            .execute()
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

        created = (
            self.service.files()
            .create(
                body=metadata,
                fields="id, name, mimeType, createdTime, modifiedTime, parents, webViewLink",
            )
            .execute()
        )

        file = self._parse_file(created)
        return Folder(**{k: v for k, v in file.__dict__.items() if not k.startswith("_")})

    # ========== Delete/Trash ==========

    def trash(self, file_id: str) -> bool:
        """Move file to trash."""
        try:
            self.service.files().update(
                fileId=file_id,
                body={"trashed": True},
            ).execute()
            logger.info(f"Trashed file {file_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"File not found for trash: {file_id}")
            else:
                logger.error(f"Error trashing file {file_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error trashing file {file_id}: {e}")
            return False

    def delete(self, file_id: str) -> bool:
        """Permanently delete file."""
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file {file_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"File not found for deletion: {file_id}")
            else:
                logger.error(f"Error deleting file {file_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting file {file_id}: {e}")
            return False

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
            True if successful
        """
        try:
            self.service.permissions().create(
                fileId=file_id,
                body={
                    "type": "user",
                    "role": role,
                    "emailAddress": email,
                },
                sendNotificationEmail=notify,
            ).execute()
            logger.info(f"Shared file {file_id} with {email} ({role})")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"File not found for sharing: {file_id}")
            elif e.resp.status == 400:
                logger.error(f"Invalid share request for {file_id}: {e}")
            else:
                logger.error(f"Error sharing file {file_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sharing file {file_id}: {e}")
            return False

    # ========== Parsing ==========

    def _parse_file(self, data: dict) -> File:
        """Parse Drive API response to File object."""
        file = DriveParser.parse_file(data)
        file._drive = self
        return file
