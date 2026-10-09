"""Drive response parsers - converts API responses to domain entities."""

from dataclasses import fields
from datetime import datetime

from gsuite_drive.file import File, Folder


class DriveParser:
    """Parser for Drive API responses."""

    @staticmethod
    def parse_file(data: dict) -> File:
        """
        Parse Drive API response to File entity.

        Args:
            data: Raw API response dict

        Returns:
            File entity
        """
        return File(
            id=data["id"],
            name=data.get("name", ""),
            mime_type=data.get("mimeType", "application/octet-stream"),
            size=int(data.get("size", 0)),
            created_time=DriveParser._parse_datetime(data.get("createdTime")),
            modified_time=DriveParser._parse_datetime(data.get("modifiedTime")),
            parents=data.get("parents", []),
            web_view_link=data.get("webViewLink"),
            web_content_link=data.get("webContentLink"),
            description=data.get("description"),
            starred=bool(data.get("starred", False)),
            trashed=bool(data.get("trashed", False)),
            md5_checksum=data.get("md5Checksum"),
        )

    @staticmethod
    def parse_folder(data: dict) -> Folder:
        """
        Parse Drive API response to Folder entity.

        Args:
            data: Raw API response dict

        Returns:
            Folder entity
        """
        return DriveParser.to_folder(DriveParser.parse_file(data))

    @staticmethod
    def to_folder(file: File) -> Folder:
        """Convert a File to a Folder, keeping every field and the client link."""
        values = {f.name: getattr(file, f.name) for f in fields(File)}
        return Folder(**values)

    @staticmethod
    def _parse_datetime(dt_string: str | None) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not dt_string:
            return None
        try:
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
