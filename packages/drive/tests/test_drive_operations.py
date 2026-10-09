"""Copy/move/update, export, permissions, uploads and folders in the Drive client."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_core.exceptions import NotFoundError, ValidationError
from gsuite_drive import EXPORT_FORMATS, Drive, File, Folder, Permission

DOC = "application/vnd.google-apps.document"
FOLDER = "application/vnd.google-apps.folder"


@pytest.fixture
def service():
    with patch("gsuite_drive.client.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture
def drive(service):
    return Drive(Mock())


def _file(id="f1", name="a.txt", mime="text/plain", **extra):
    return {"id": id, "name": name, "mimeType": mime, **extra}


class TestMetadata:
    def test_update_sends_only_given_fields(self, drive, service):
        service.files().update().execute.return_value = _file(name="b.txt", starred=True)

        updated = drive.update("f1", name="b.txt", starred=True)

        assert service.files().update.call_args.kwargs["body"] == {"name": "b.txt", "starred": True}
        assert updated.name == "b.txt"
        assert updated.starred is True

    def test_rename(self, drive, service):
        service.files().update().execute.return_value = _file(name="new")
        drive.rename("f1", "new")
        assert service.files().update.call_args.kwargs["body"] == {"name": "new"}

    def test_copy(self, drive, service):
        service.files().copy().execute.return_value = _file(id="f2", name="copy")

        copied = drive.copy("f1", name="copy", parent_id="dir")

        kwargs = service.files().copy.call_args.kwargs
        assert kwargs["fileId"] == "f1"
        assert kwargs["body"] == {"name": "copy", "parents": ["dir"]}
        assert kwargs["supportsAllDrives"] is True
        assert copied.id == "f2"

    def test_move_replaces_all_parents(self, drive, service):
        service.files().get().execute.return_value = {"parents": ["old1", "old2"]}
        service.files().update().execute.return_value = _file(parents=["new"])

        moved = drive.move("f1", "new")

        kwargs = service.files().update.call_args.kwargs
        assert kwargs["addParents"] == "new"
        assert kwargs["removeParents"] == "old1,old2"
        assert moved.parents == ["new"]

    def test_restore(self, drive, service):
        assert drive.restore("f1") is True
        assert service.files().update.call_args.kwargs["body"] == {"trashed": False}

    def test_restore_missing(self, drive, service, http_error):
        service.files().update().execute.side_effect = http_error(404)
        assert drive.restore("gone") is False

    def test_new_fields_are_parsed(self, drive, service):
        service.files().get().execute.return_value = _file(
            description="notes", trashed=True, md5Checksum="abc"
        )
        file = drive.get("f1")
        assert (file.description, file.trashed, file.md5_checksum) == ("notes", True, "abc")


class TestListingFilters:
    def _query(self, service):
        return service.files().list.call_args.kwargs["q"]

    def test_only_trashed(self, drive, service):
        service.files().list().execute.return_value = {"files": []}
        drive.list_files(trashed=True)
        assert self._query(service) == "trashed=true"

    def test_trashed_and_not(self, drive, service):
        service.files().list().execute.return_value = {"files": []}
        drive.list_files(trashed=None, parent_id="p")
        assert self._query(service) == "'p' in parents"

    def test_shared_drives_included(self, drive, service):
        service.files().list().execute.return_value = {"files": []}
        drive.list_files()
        kwargs = service.files().list.call_args.kwargs
        assert kwargs["supportsAllDrives"] is True
        assert kwargs["includeItemsFromAllDrives"] is True


class TestExport:
    def test_short_format(self, drive, service):
        service.files().export().execute.return_value = b"%PDF"

        assert drive.export("doc1", "pdf") == b"%PDF"
        assert service.files().export.call_args.kwargs == {
            "fileId": "doc1",
            "mimeType": "application/pdf",
        }

    def test_mime_type_passthrough(self, drive, service):
        service.files().export().execute.return_value = b"x"
        drive.export("doc1", "text/csv")
        assert service.files().export.call_args.kwargs["mimeType"] == "text/csv"

    def test_unknown_format(self, drive):
        with pytest.raises(ValidationError, match="unknown export format"):
            drive.export("doc1", "doc")

    def test_download_with_export(self, drive, service, tmp_path):
        service.files().export().execute.return_value = b"data"

        path = drive.download("doc1", str(tmp_path / "out.docx"), export_format="docx")

        assert open(path, "rb").read() == b"data"
        assert service.files().export.call_args.kwargs["mimeType"] == EXPORT_FORMATS["docx"]

    def test_google_doc_downloads_as_export_by_default(self, drive, service, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        service.files().export().execute.return_value = b"docx-bytes"
        doc = drive._parse_file(_file(id="d1", name="Plan", mime=DOC))

        path = doc.download()

        assert path == "Plan.docx"
        assert (tmp_path / "Plan.docx").read_bytes() == b"docx-bytes"


class TestPermissions:
    def test_list(self, drive, service):
        service.permissions().list().execute.return_value = {
            "permissions": [
                {"id": "p1", "type": "user", "role": "owner", "emailAddress": "me@x.com"}
            ]
        }

        perms = drive.list_permissions("f1")

        assert perms == [Permission(id="p1", type="user", role="owner", email_address="me@x.com")]

    def test_anyone_with_link(self, drive, service):
        service.permissions().create().execute.return_value = {
            "id": "anyoneWithLink",
            "type": "anyone",
            "role": "reader",
        }

        perm = drive.add_permission("f1", type="anyone")

        kwargs = service.permissions().create.call_args.kwargs
        assert kwargs["body"] == {"type": "anyone", "role": "reader"}
        # sendNotificationEmail is only valid for users and groups
        assert "sendNotificationEmail" not in kwargs
        assert perm.type == "anyone"

    def test_domain(self, drive, service):
        service.permissions().create().execute.return_value = {
            "id": "p",
            "type": "domain",
            "role": "reader",
        }
        drive.add_permission("f1", type="domain", domain="example.com")
        assert service.permissions().create.call_args.kwargs["body"]["domain"] == "example.com"

    @pytest.mark.parametrize(
        ("kwargs", "field"), [({"type": "user"}, "email"), ({"type": "domain"}, "domain")]
    )
    def test_validation(self, drive, kwargs, field):
        with pytest.raises(ValidationError) as exc_info:
            drive.add_permission("f1", **kwargs)
        assert exc_info.value.field == field

    def test_remove(self, drive, service):
        assert drive.remove_permission("f1", "p1") is True
        assert service.permissions().delete.call_args.kwargs["permissionId"] == "p1"

    def test_remove_missing(self, drive, service, http_error):
        service.permissions().delete().execute.side_effect = http_error(404)
        assert drive.remove_permission("f1", "p1") is False


class TestUpload:
    def test_chunks_report_progress(self, drive, service):
        progress = []
        chunk = Mock()
        chunk.progress.side_effect = [0.25, 0.75]
        service.files().create().next_chunk.side_effect = [
            (chunk, None),
            (chunk, None),
            (None, _file(id="up")),
        ]

        with patch("gsuite_drive.client.MediaIoBaseUpload"):
            uploaded = drive.upload_content(b"x" * 10, "x.bin", on_progress=progress.append)

        assert uploaded.id == "up"
        assert progress == [0.25, 0.75, 1.0]
        # Each chunk retries itself; safe because resumable uploads resume
        assert service.files().create().next_chunk.call_args.kwargs["num_retries"] >= 1

    def test_errors_are_mapped(self, drive, service, http_error):
        from gsuite_core.exceptions import PermissionDeniedError

        service.files().create().next_chunk.side_effect = http_error(403, "storageQuotaExceeded")

        with patch("gsuite_drive.client.MediaIoBaseUpload"), pytest.raises(PermissionDeniedError):
            drive.upload_content(b"x", "x.bin")


class TestFolders:
    def test_created_folder_is_linked(self, drive, service):
        service.files().create().execute.return_value = _file(id="dir", name="D", mime=FOLDER)
        service.files().list().execute.return_value = {"files": []}

        folder = drive.create_folder("D")

        assert isinstance(folder, Folder)
        # Used to raise "Folder not linked to Drive client"
        assert folder.list_files() == []

    def test_listed_folders_are_linked(self, drive):
        with patch.object(
            Drive, "iter_files", return_value=iter([drive._parse_file(_file(mime=FOLDER))])
        ):
            folders = drive.list_folders()
        assert folders[0]._drive is drive

    def test_recursive_listing(self, drive):
        tree = {
            "root": [_file("a", "a.txt"), _file("sub", "sub", FOLDER)],
            "sub": [_file("b", "b.txt"), _file("root", "loop", FOLDER)],
        }

        def iter_files(parent_id=None, max_results=None):
            return (drive._parse_file(f) for f in tree.get(parent_id, []))

        folder = Folder(id="root", name="root", mime_type=FOLDER, _drive=drive)
        with patch.object(Drive, "iter_files", side_effect=iter_files):
            flat = [f.id for f in folder.list_files()]
            deep = [f.id for f in folder.list_files(recursive=True)]

        assert flat == ["a", "sub"]
        # "loop" points back at root; it is listed but not descended into again
        assert deep == ["a", "sub", "b", "root"]


def test_missing_file_download_raises(drive, service, http_error):
    with patch("gsuite_drive.client.MediaIoBaseDownload") as downloader:
        downloader.return_value.next_chunk.side_effect = http_error(404)
        with pytest.raises(NotFoundError):
            drive.get_content("gone")


def test_file_is_exported_type():
    assert File(id="x", name="n", mime_type=DOC).is_google_doc
