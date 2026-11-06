"""Drive REST routes with a mocked Drive client."""

from datetime import UTC, datetime

import httpx
import pytest

from gsuite_api import dependencies
from gsuite_drive import AsyncDrive, File, Permission

DOC = "application/vnd.google-apps.document"


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


def _file(**overrides) -> File:
    fields = {
        "id": "f1",
        "name": "report.pdf",
        "mime_type": "application/pdf",
        "size": 4,
        "parents": ["root"],
        "modified_time": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return File(**fields)


@pytest.fixture
def drive(services):
    return services["drive"]


def test_list_files(client, drive):
    drive.list_files.return_value = [_file()]

    response = client.get("/drive/files", params={"parent_id": "root", "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["files"][0]["modified_time"] == "2026-01-01T00:00:00+00:00"
    drive.list_files.assert_called_once_with(
        query=None, parent_id="root", mime_type=None, max_results=10, trashed=False
    )


def test_get_file(client, drive):
    drive.get.return_value = _file()
    assert client.get("/drive/files/f1").json()["name"] == "report.pdf"


def test_get_missing_file(client, drive):
    drive.get.return_value = None
    assert client.get("/drive/files/nope").status_code == 404


def test_download_binary(client, drive):
    drive.get.return_value = _file()
    drive.get_content.return_value = b"%PDF"

    response = client.get("/drive/files/f1/content")

    assert response.content == b"%PDF"
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="report.pdf"' in response.headers["content-disposition"]
    drive.export.assert_not_called()


def test_google_doc_is_exported(client, drive):
    drive.get.return_value = _file(name="Plan", mime_type=DOC)
    drive.export.return_value = b"docx"

    response = client.get("/drive/files/f1/content")

    assert response.content == b"docx"
    drive.export.assert_called_once_with("f1", "docx")
    assert 'filename="Plan.docx"' in response.headers["content-disposition"]


def test_explicit_export_format(client, drive):
    drive.get.return_value = _file(name="Plan", mime_type=DOC)
    drive.export.return_value = b"%PDF"

    response = client.get("/drive/files/f1/content", params={"export": "pdf"})

    assert response.headers["content-type"] == "application/pdf"
    drive.export.assert_called_once_with("f1", "pdf")


def test_upload_reaches_drive_whole_through_the_real_async_client(make_client, settings):
    """The UploadFile stream goes through AsyncDrive's resumable upload unchanged."""
    received = bytearray()
    session = "https://www.googleapis.com/upload/drive/v3/files?upload_id=s1"

    def google(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, headers={"location": session})
        received.extend(request.content)
        body = {"id": "new", "name": "big.bin", "mimeType": "application/octet-stream"}
        return httpx.Response(200, json=body)

    payload = bytes(range(256)) * 4096  # 1 MiB, past the in-memory spool limit
    test_client = make_client(settings)
    drive = AsyncDrive(FakeCredentials(), transport=httpx.MockTransport(google))
    test_client.app.dependency_overrides[dependencies.get_drive] = lambda: drive

    response = test_client.post(
        "/drive/files/upload",
        headers={"X-API-Key": settings.api_key},
        files={"file": ("big.bin", payload, "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "new"
    assert bytes(received) == payload


def test_upload(client, drive):
    drive.upload_content.return_value = _file(id="new", name="notes.txt", mime_type="text/plain")

    response = client.post(
        "/drive/files/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"parent_id": "dir"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "new"
    kwargs = drive.upload_content.call_args.kwargs
    assert (kwargs["name"], kwargs["parent_id"], kwargs["mime_type"]) == (
        "notes.txt",
        "dir",
        "text/plain",
    )


def test_update_sends_only_given_fields(client, drive):
    drive.update.return_value = _file(name="new.pdf")

    client.patch("/drive/files/f1", json={"name": "new.pdf"})

    drive.update.assert_called_once_with("f1", name="new.pdf")


def test_copy_and_move(client, drive):
    drive.copy.return_value = _file(id="f2")
    drive.move.return_value = _file(parents=["dir"])

    assert client.post("/drive/files/f1/copy", json={"name": "c"}).json()["id"] == "f2"
    assert client.post("/drive/files/f1/move", json={"parent_id": "dir"}).json()["parents"] == [
        "dir"
    ]
    drive.move.assert_called_once_with("f1", "dir")


def test_delete_trashes_by_default(client, drive):
    drive.trash.return_value = True

    response = client.delete("/drive/files/f1")

    assert response.json() == {"id": "f1", "deleted": False, "trashed": True}
    drive.delete.assert_not_called()


def test_permanent_delete(client, drive):
    drive.delete.return_value = True
    assert client.delete("/drive/files/f1", params={"permanent": True}).json()["deleted"] is True


@pytest.mark.parametrize(
    ("method", "path", "client_method"),
    [
        ("POST", "/drive/files/f1/trash", "trash"),
        ("POST", "/drive/files/f1/restore", "restore"),
        ("DELETE", "/drive/files/f1", "trash"),
        ("DELETE", "/drive/files/f1/permissions/p1", "remove_permission"),
    ],
)
def test_missing_resources_are_404(client, drive, method, path, client_method):
    getattr(drive, client_method).return_value = False
    assert client.request(method, path).status_code == 404


def test_create_folder(client, drive):
    drive.create_folder.return_value = _file(
        id="dir", name="D", mime_type="application/vnd.google-apps.folder"
    )
    assert client.post("/drive/folders", json={"name": "D"}).json()["id"] == "dir"


def test_permissions(client, drive):
    drive.list_permissions.return_value = [
        Permission(id="p1", type="user", role="owner", email_address="me@x.com")
    ]
    drive.add_permission.return_value = Permission(
        id="anyoneWithLink", type="anyone", role="reader"
    )

    listed = client.get("/drive/files/f1/permissions").json()
    added = client.post("/drive/files/f1/permissions", json={"type": "anyone"}).json()

    assert listed["permissions"][0]["email_address"] == "me@x.com"
    assert added["type"] == "anyone"


@pytest.mark.parametrize(
    "body",
    [{"role": "owner"}, {"type": "user", "email": "not-an-email"}, {"type": "robot"}],
)
def test_permission_request_validation(client, body):
    assert client.post("/drive/files/f1/permissions", json=body).status_code == 422


def test_sdk_validation_error_is_422(client, drive):
    from gsuite_core.exceptions import ValidationError

    drive.add_permission.side_effect = ValidationError("email", "required for type='user'")

    response = client.post("/drive/files/f1/permissions", json={"type": "user"})

    assert response.status_code == 422
    assert response.json()["field"] == "email"
