"""Drive File and Folder entities."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from gsuite_drive.client import Drive


@dataclass
class File:
    """
    Google Drive file.

    Represents a file in Google Drive with methods for
    download, update, and management.
    """

    id: str
    name: str
    mime_type: str
    size: int = 0
    created_time: datetime | None = None
    modified_time: datetime | None = None
    parents: list[str] = field(default_factory=list)
    web_view_link: str | None = None
    web_content_link: str | None = None

    _drive: Optional["Drive"] = field(default=None, repr=False)

    @property
    def is_folder(self) -> bool:
        """Check if this is a folder."""
        return self.mime_type == "application/vnd.google-apps.folder"

    @property
    def is_google_doc(self) -> bool:
        """Check if this is a Google Docs file."""
        return self.mime_type.startswith("application/vnd.google-apps.")

    def download(self, path: str | None = None) -> str:
        """
        Download file to local path.

        Args:
            path: Local path (default: current dir with original name)

        Returns:
            Path where file was saved
        """
        if not self._drive:
            raise RuntimeError("File not linked to Drive client")
        return self._drive.download(self.id, path or self.name)

    def get_content(self) -> bytes:
        """
        Get file content as bytes.

        Returns:
            File content
        """
        if not self._drive:
            raise RuntimeError("File not linked to Drive client")
        return self._drive.get_content(self.id)

    def trash(self) -> "File":
        """Move file to trash."""
        if self._drive:
            self._drive.trash(self.id)
        return self

    def delete(self) -> None:
        """Permanently delete file."""
        if self._drive:
            self._drive.delete(self.id)


@dataclass
class Folder(File):
    """
    Google Drive folder.

    A folder is a special type of file.
    """

    def __post_init__(self):
        """Ensure mime type is folder."""
        self.mime_type = "application/vnd.google-apps.folder"

    def list_files(self, recursive: bool = False) -> list[File]:
        """
        List files in this folder.

        Args:
            recursive: Include files in subfolders

        Returns:
            List of files
        """
        if not self._drive:
            raise RuntimeError("Folder not linked to Drive client")
        return self._drive.list_files(parent_id=self.id)
