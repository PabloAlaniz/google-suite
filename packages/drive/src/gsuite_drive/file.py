"""Drive File and Folder entities."""

from collections.abc import Iterator
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
    description: str | None = None
    starred: bool = False
    trashed: bool = False
    md5_checksum: str | None = None

    _drive: Optional["Drive"] = field(default=None, repr=False)

    @property
    def is_folder(self) -> bool:
        """Check if this is a folder."""
        return self.mime_type == "application/vnd.google-apps.folder"

    @property
    def is_google_doc(self) -> bool:
        """Check if this is a Google Docs file."""
        return self.mime_type.startswith("application/vnd.google-apps.")

    def download(self, path: str | None = None, export_format: str | None = None) -> str:
        """
        Download file to local path.

        Google Docs, Sheets and Slides can't be downloaded as-is; they are
        exported (by default to docx/xlsx/pptx, or `export_format`).

        Args:
            path: Local path (default: current dir with original name,
                plus the export extension for Google files)
            export_format: Export format for Google files ("pdf", "docx", ...)

        Returns:
            Path where file was saved
        """
        if not self._drive:
            raise RuntimeError("File not linked to Drive client")

        from gsuite_drive.client import default_export_format

        if self.is_google_doc and export_format is None:
            export_format = default_export_format(self.mime_type)
        if path is None:
            path = f"{self.name}.{export_format}" if export_format else self.name
        return self._drive.download(self.id, path, export_format=export_format)

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

    def __post_init__(self) -> None:
        """Ensure mime type is folder."""
        self.mime_type = "application/vnd.google-apps.folder"

    def list_files(self, recursive: bool = False) -> list[File]:
        """
        List files in this folder.

        Args:
            recursive: Include files in subfolders (subfolders themselves are
                listed too)

        Returns:
            List of files
        """
        return list(self.iter_files(recursive))

    def iter_files(self, recursive: bool = False) -> Iterator[File]:
        """Lazily yield files in this folder, breadth-first if recursive."""
        if not self._drive:
            raise RuntimeError("Folder not linked to Drive client")

        pending = [self.id]
        seen = {self.id}  # a file can have several parents; don't loop
        while pending:
            folder_id = pending.pop(0)
            for file in self._drive.iter_files(parent_id=folder_id, max_results=None):
                yield file
                if recursive and file.is_folder and file.id not in seen:
                    seen.add(file.id)
                    pending.append(file.id)
