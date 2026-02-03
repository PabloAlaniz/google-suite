"""Drive response parsers - converts API responses to domain entities."""

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
        file = DriveParser.parse_file(data)
        return Folder(
            id=file.id,
            name=file.name,
            mime_type=file.mime_type,
            size=file.size,
            created_time=file.created_time,
            modified_time=file.modified_time,
            parents=file.parents,
            web_view_link=file.web_view_link,
            web_content_link=file.web_content_link,
        )

    @staticmethod
    def _parse_datetime(dt_string: str | None) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not dt_string:
            return None
        try:
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
