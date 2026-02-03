"""Tests for Drive client."""

from datetime import datetime
from unittest.mock import Mock, patch

from gsuite_drive.client import Drive
from gsuite_drive.file import File, Folder


class TestDriveInit:
    """Tests for Drive client initialization."""

    def test_init_with_auth(self):
        """Test Drive client initialization."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        assert drive.auth is mock_auth
        assert drive._service is None


class TestDriveService:
    """Tests for Drive service property."""

    @patch("gsuite_drive.client.build")
    def test_lazy_service_creation(self, mock_build):
        """Test service is created lazily."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_service = Mock()
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)

        # Service not created yet
        mock_build.assert_not_called()

        # Access service
        service = drive.service

        # Now it's created
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_auth.credentials)
        assert service is mock_service


class TestListFiles:
    """Tests for list_files method."""

    @patch("gsuite_drive.client.build")
    def test_list_files_empty(self, mock_build):
        """Test list_files with no results."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().list().execute.return_value = {"files": []}
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        files = drive.list_files()

        assert files == []

    @patch("gsuite_drive.client.build")
    def test_list_files_with_parent(self, mock_build):
        """Test list_files with parent filter."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.files().list
        mock_list().execute.return_value = {"files": []}
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        drive.list_files(parent_id="folder123")

        call_kwargs = mock_list.call_args[1]
        assert "'folder123' in parents" in call_kwargs.get("q", "")

    @patch("gsuite_drive.client.build")
    def test_list_files_with_mime_type(self, mock_build):
        """Test list_files with mime type filter."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.files().list
        mock_list().execute.return_value = {"files": []}
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        drive.list_files(mime_type="application/pdf")

        call_kwargs = mock_list.call_args[1]
        assert "mimeType='application/pdf'" in call_kwargs.get("q", "")

    @patch("gsuite_drive.client.build")
    def test_list_files_excludes_trashed(self, mock_build):
        """Test list_files excludes trashed files."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.files().list
        mock_list().execute.return_value = {"files": []}
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        drive.list_files()

        call_kwargs = mock_list.call_args[1]
        assert "trashed=false" in call_kwargs.get("q", "")

    @patch("gsuite_drive.client.build")
    def test_list_files_returns_file_objects(self, mock_build):
        """Test list_files returns File objects."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "document.pdf",
                    "mimeType": "application/pdf",
                    "size": "1024",
                    "createdTime": "2026-01-28T10:00:00.000Z",
                    "modifiedTime": "2026-01-28T11:00:00.000Z",
                },
                {
                    "id": "file2",
                    "name": "image.png",
                    "mimeType": "image/png",
                    "size": "2048",
                },
            ]
        }
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        files = drive.list_files()

        assert len(files) == 2
        assert all(isinstance(f, File) for f in files)
        assert files[0].name == "document.pdf"
        assert files[0].size == 1024


class TestListFolders:
    """Tests for list_folders method."""

    @patch.object(Drive, "list_files")
    def test_list_folders(self, mock_list):
        """Test list_folders filters by folder mime type."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        mock_list.return_value = []
        drive.list_folders()

        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("mime_type") == "application/vnd.google-apps.folder"


class TestSearch:
    """Tests for search method."""

    @patch.object(Drive, "list_files")
    def test_search_contains(self, mock_list):
        """Test search with contains."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        mock_list.return_value = []
        drive.search("report")

        call_kwargs = mock_list.call_args[1]
        assert "name contains 'report'" in call_kwargs.get("query", "")

    @patch.object(Drive, "list_files")
    def test_search_exact(self, mock_list):
        """Test search with exact match."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        mock_list.return_value = []
        drive.search("report.pdf", exact=True)

        call_kwargs = mock_list.call_args[1]
        assert "name='report.pdf'" in call_kwargs.get("query", "")


class TestGetFile:
    """Tests for get method."""

    @patch("gsuite_drive.client.build")
    def test_get_file(self, mock_build):
        """Test getting a file by ID."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().get().execute.return_value = {
            "id": "file123",
            "name": "test.txt",
            "mimeType": "text/plain",
            "size": "100",
        }
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        file = drive.get("file123")

        assert isinstance(file, File)
        assert file.id == "file123"
        assert file.name == "test.txt"

    @patch("gsuite_drive.client.build")
    def test_get_file_not_found(self, mock_build):
        """Test getting non-existent file."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().get().execute.side_effect = Exception("Not found")
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        file = drive.get("nonexistent")

        assert file is None


class TestUpload:
    """Tests for upload methods."""

    @patch("gsuite_drive.client.build")
    @patch("gsuite_drive.client.MediaFileUpload")
    def test_upload_file(self, mock_media, mock_build):
        """Test uploading a file."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().create().execute.return_value = {
            "id": "new_file",
            "name": "uploaded.txt",
            "mimeType": "text/plain",
        }
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        file = drive.upload("/tmp/test.txt")

        assert isinstance(file, File)
        assert file.id == "new_file"
        mock_media.assert_called_once()

    @patch("gsuite_drive.client.build")
    @patch("gsuite_drive.client.MediaFileUpload")
    def test_upload_with_parent(self, mock_media, mock_build):
        """Test uploading to specific folder."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_create = mock_service.files().create
        mock_create().execute.return_value = {
            "id": "new_file",
            "name": "test.txt",
            "mimeType": "text/plain",
        }
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        drive.upload("/tmp/test.txt", parent_id="folder123")

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["body"]["parents"] == ["folder123"]


class TestCreateFolder:
    """Tests for create_folder method."""

    @patch("gsuite_drive.client.build")
    def test_create_folder(self, mock_build):
        """Test creating a folder."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().create().execute.return_value = {
            "id": "folder_id",
            "name": "New Folder",
            "mimeType": "application/vnd.google-apps.folder",
        }
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        folder = drive.create_folder("New Folder")

        assert isinstance(folder, Folder)
        assert folder.name == "New Folder"

        # Verify correct mime type was set
        call_kwargs = mock_service.files().create.call_args[1]
        assert call_kwargs["body"]["mimeType"] == "application/vnd.google-apps.folder"


class TestTrashAndDelete:
    """Tests for trash and delete methods."""

    @patch("gsuite_drive.client.build")
    def test_trash(self, mock_build):
        """Test moving file to trash."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        result = drive.trash("file123")

        assert result is True

        call_kwargs = mock_service.files().update.call_args[1]
        assert call_kwargs["body"]["trashed"] is True

    @patch("gsuite_drive.client.build")
    def test_delete(self, mock_build):
        """Test permanent deletion."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        result = drive.delete("file123")

        assert result is True
        mock_service.files().delete.assert_called()

    @patch("gsuite_drive.client.build")
    def test_delete_failure(self, mock_build):
        """Test delete failure."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.files().delete().execute.side_effect = Exception("Error")
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        result = drive.delete("file123")

        assert result is False


class TestShare:
    """Tests for share method."""

    @patch("gsuite_drive.client.build")
    def test_share_file(self, mock_build):
        """Test sharing a file."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        result = drive.share("file123", "user@example.com", role="writer")

        assert result is True

        call_kwargs = mock_service.permissions().create.call_args[1]
        assert call_kwargs["body"]["emailAddress"] == "user@example.com"
        assert call_kwargs["body"]["role"] == "writer"

    @patch("gsuite_drive.client.build")
    def test_share_failure(self, mock_build):
        """Test share failure."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.permissions().create().execute.side_effect = Exception("Error")
        mock_build.return_value = mock_service

        drive = Drive(mock_auth)
        result = drive.share("file123", "user@example.com")

        assert result is False


class TestParseFile:
    """Tests for file parsing."""

    def test_parse_file_basic(self):
        """Test parsing basic file data."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        data = {
            "id": "file123",
            "name": "test.txt",
            "mimeType": "text/plain",
            "size": "1024",
        }

        file = drive._parse_file(data)

        assert file.id == "file123"
        assert file.name == "test.txt"
        assert file.mime_type == "text/plain"
        assert file.size == 1024

    def test_parse_file_with_times(self):
        """Test parsing file with timestamps."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        data = {
            "id": "file123",
            "name": "test.txt",
            "mimeType": "text/plain",
            "createdTime": "2026-01-28T10:00:00.000Z",
            "modifiedTime": "2026-01-28T11:00:00.000Z",
        }

        file = drive._parse_file(data)

        assert file.created_time is not None
        assert file.modified_time is not None
        assert isinstance(file.created_time, datetime)

    def test_parse_file_links_to_client(self):
        """Test parsed file is linked to Drive client."""
        mock_auth = Mock()
        drive = Drive(mock_auth)

        data = {
            "id": "file123",
            "name": "test.txt",
            "mimeType": "text/plain",
        }

        file = drive._parse_file(data)

        assert file._drive is drive
