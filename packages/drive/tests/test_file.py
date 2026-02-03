"""Tests for Drive File entity."""

from datetime import datetime

import pytest

from gsuite_drive.file import File, Folder


class TestFile:
    """Tests for File entity."""

    @pytest.fixture
    def sample_file(self):
        """Create a sample file."""
        return File(
            id="file123",
            name="document.pdf",
            mime_type="application/pdf",
            size=1024,
            created_time=datetime(2026, 1, 1, 10, 0, 0),
            modified_time=datetime(2026, 1, 28, 15, 30, 0),
            parents=["folder123"],
            web_view_link="https://drive.google.com/file/d/file123/view",
        )

    def test_is_folder_false(self, sample_file):
        """Test is_folder for regular file."""
        assert sample_file.is_folder is False

    def test_is_folder_true(self):
        """Test is_folder for folder."""
        folder = File(
            id="folder123",
            name="My Folder",
            mime_type="application/vnd.google-apps.folder",
        )
        assert folder.is_folder is True

    def test_is_google_doc(self):
        """Test is_google_doc detection."""
        doc = File(
            id="doc123",
            name="My Doc",
            mime_type="application/vnd.google-apps.document",
        )
        assert doc.is_google_doc is True

        sheet = File(
            id="sheet123",
            name="My Sheet",
            mime_type="application/vnd.google-apps.spreadsheet",
        )
        assert sheet.is_google_doc is True

    def test_download_without_client(self, sample_file):
        """Test download raises error without Drive client."""
        with pytest.raises(RuntimeError, match="not linked"):
            sample_file.download()

    def test_get_content_without_client(self, sample_file):
        """Test get_content raises error without Drive client."""
        with pytest.raises(RuntimeError, match="not linked"):
            sample_file.get_content()


class TestFolder:
    """Tests for Folder entity."""

    def test_folder_mime_type(self):
        """Test folder has correct mime type."""
        folder = Folder(
            id="folder123",
            name="My Folder",
            mime_type="",  # Will be overwritten
        )
        assert folder.mime_type == "application/vnd.google-apps.folder"
        assert folder.is_folder is True

    def test_list_files_without_client(self):
        """Test list_files raises error without Drive client."""
        folder = Folder(id="folder123", name="Test", mime_type="")

        with pytest.raises(RuntimeError, match="not linked"):
            folder.list_files()
