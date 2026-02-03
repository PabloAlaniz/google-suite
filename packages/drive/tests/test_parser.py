"""Tests for Drive parser."""

import pytest

from gsuite_drive.parser import DriveParser


class TestDriveParser:
    """Tests for DriveParser."""

    def test_parse_file_basic(self):
        """Test parsing a basic file."""
        data = {
            "id": "file123",
            "name": "document.pdf",
            "mimeType": "application/pdf",
            "size": "12345",
            "createdTime": "2026-01-15T10:00:00.000Z",
            "modifiedTime": "2026-02-01T14:30:00.000Z",
            "parents": ["folder456"],
            "webViewLink": "https://drive.google.com/file/d/file123/view",
            "webContentLink": "https://drive.google.com/uc?id=file123",
        }

        file = DriveParser.parse_file(data)

        assert file.id == "file123"
        assert file.name == "document.pdf"
        assert file.mime_type == "application/pdf"
        assert file.size == 12345
        assert file.parents == ["folder456"]
        assert file.web_view_link is not None
        assert file.created_time.month == 1
        assert file.modified_time.month == 2

    def test_parse_file_minimal(self):
        """Test parsing a file with minimal data."""
        data = {
            "id": "file789",
            "name": "test.txt",
        }

        file = DriveParser.parse_file(data)

        assert file.id == "file789"
        assert file.name == "test.txt"
        assert file.mime_type == "application/octet-stream"
        assert file.size == 0
        assert file.parents == []
        assert file.created_time is None

    def test_parse_folder(self):
        """Test parsing a folder."""
        data = {
            "id": "folder123",
            "name": "My Folder",
            "mimeType": "application/vnd.google-apps.folder",
            "createdTime": "2026-01-01T00:00:00.000Z",
        }

        folder = DriveParser.parse_folder(data)

        assert folder.id == "folder123"
        assert folder.name == "My Folder"
        assert folder.mime_type == "application/vnd.google-apps.folder"

    def test_parse_datetime_with_z(self):
        """Test parsing datetime with Z suffix."""
        dt = DriveParser._parse_datetime("2026-02-03T10:30:00.000Z")

        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 3

    def test_parse_datetime_none(self):
        """Test parsing None datetime."""
        dt = DriveParser._parse_datetime(None)
        assert dt is None

    def test_parse_datetime_invalid(self):
        """Test parsing invalid datetime."""
        dt = DriveParser._parse_datetime("not a date")
        assert dt is None
