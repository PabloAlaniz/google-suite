"""AsyncDrive against a fake Drive REST API (httpx.MockTransport)."""

import io
import json
import re
from unittest.mock import patch

import httpx
import pytest

from gsuite_core import Settings
from gsuite_core.exceptions import PermissionDeniedError, ValidationError
from gsuite_drive import AsyncDrive, File, Folder

KIB = 1024
CHUNK = 256 * KIB
SESSION = "https://www.googleapis.com/upload/drive/v3/files?upload_id=s1"


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


def raw_file(fid="f1", name="report.pdf", mime="application/pdf", **extra):
    return {"id": fid, "name": name, "mimeType": mime, "parents": ["root"], **extra}


def error(status):
    return httpx.Response(status, json={"error": {"code": status, "message": "nope"}})


class FakeDriveApi:
    """Routes for the metadata API plus one resumable upload session."""

    def __init__(self):
        self.calls = []
        self.files = {"f1": raw_file()}
        self.received = bytearray()
        self.upload_meta = None
        self.upload_headers = None
        # (chunk number, bytes kept before failing, status) for one injected failure
        self.fail_chunk: tuple[int, int, int] | None = None
        self.chunks = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = request.content
        self.calls.append((request.method, request.url.path, dict(request.url.params), body))
        if url.startswith(SESSION):
            return self._chunk(request)
        if request.url.path == "/upload/drive/v3/files":
            self.upload_meta = json.loads(body)
            self.upload_headers = dict(request.headers)
            return httpx.Response(200, headers={"location": SESSION})

        path = request.url.path.removeprefix("/drive/v3/")
        data = json.loads(body) if body else None
        for (method, pattern), route in self.routes().items():
            match = re.fullmatch(pattern, path)
            if request.method == method and match:
                return route(request, data, *match.groups())
        return error(404)

    def routes(self):
        def found(fid, payload):
            return httpx.Response(200, json=payload) if fid in self.files else error(404)

        return {
            ("GET", "files"): lambda r, d: httpx.Response(
                200, json={"files": list(self.files.values())}
            ),
            ("GET", r"files/(\w+)"): lambda r, d, fid: (
                httpx.Response(200, content=b"PDF-BYTES")
                if r.url.params.get("alt") == "media" and fid in self.files
                else found(fid, self.files.get(fid))
            ),
            ("GET", r"files/(\w+)/export"): lambda r, d, fid: httpx.Response(
                200, content=f"export:{r.url.params['mimeType']}".encode()
            ),
            ("PATCH", r"files/(\w+)"): lambda r, d, fid: found(fid, {**raw_file(fid), **(d or {})}),
            ("POST", r"files/(\w+)/copy"): lambda r, d, fid: httpx.Response(
                200, json=raw_file("f2", d.get("name", "Copy"))
            ),
            ("POST", "files"): lambda r, d: httpx.Response(
                200, json=raw_file("dir", d["name"], d["mimeType"])
            ),
            ("DELETE", r"files/(\w+)"): lambda r, d, fid: (
                httpx.Response(204) if fid in self.files else error(404)
            ),
            ("GET", r"files/(\w+)/permissions"): lambda r, d, fid: httpx.Response(
                200, json={"permissions": [{"id": "p1", "type": "anyone", "role": "reader"}]}
            ),
            ("POST", r"files/(\w+)/permissions"): lambda r, d, fid: (
                httpx.Response(200, json={"id": "p2", **d}) if fid in self.files else error(404)
            ),
            ("DELETE", r"files/(\w+)/permissions/(\w+)"): lambda r, d, fid, pid: (
                httpx.Response(204) if pid == "p1" else error(404)
            ),
        }

    def _chunk(self, request: httpx.Request) -> httpx.Response:
        content_range = request.headers["content-range"]
        total = int(content_range.rsplit("/", 1)[1])
        if not content_range.startswith("bytes */"):  # a data chunk, not a status query
            start = int(content_range.split(" ")[1].split("-")[0])
            assert start == len(self.received), "sent a range Drive doesn't expect"
            self.chunks += 1
            if self.fail_chunk and self.fail_chunk[0] == self.chunks:
                _, kept, status = self.fail_chunk
                self.fail_chunk = None
                self.received += request.content[:kept]
                return error(status)
            self.received += request.content
        if len(self.received) < total:
            headers = {"range": f"bytes=0-{len(self.received) - 1}"} if self.received else {}
            return httpx.Response(308, headers=headers)
        return httpx.Response(200, json=raw_file("up", self.upload_meta["name"]))

    def last(self, method):
        return next(call for call in reversed(self.calls) if call[0] == method)


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=3, retry_delay=0.0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


@pytest.fixture
def api():
    return FakeDriveApi()


@pytest.fixture
async def drive(api):
    transport = httpx.MockTransport(api.handler)
    async with AsyncDrive(FakeCredentials(), chunk_size=CHUNK, transport=transport) as client:
        yield client


class TestReading:
    async def test_list_files_sends_the_sync_query(self, drive, api):
        files = await drive.list_files(parent_id="dir", mime_type="application/pdf")

        assert [f.name for f in files] == ["report.pdf"]
        _, _, params, _ = api.calls[0]
        assert params["q"] == ("'dir' in parents and mimeType='application/pdf' and trashed=false")
        assert params["fields"].startswith("nextPageToken, files(")
        assert (params["supportsAllDrives"], params["includeItemsFromAllDrives"]) == (
            "true",
            "true",
        )
        assert params["pageSize"] == "100"

    async def test_search_quotes_the_name(self, drive, api):
        await drive.search("O'Brien")

        assert api.calls[0][2]["q"].startswith(r"(name contains 'O\'Brien')")

    async def test_get_content_export_and_download(self, drive, api, tmp_path):
        assert (await drive.get("f1")).name == "report.pdf"
        assert await drive.get("nope") is None
        assert await drive.get_content("f1") == b"PDF-BYTES"
        assert await drive.export("f1", "csv") == b"export:text/csv"

        target = tmp_path / "out.docx"
        assert await drive.download("f1", str(target), export_format="docx") == str(target)
        assert target.read_bytes().startswith(b"export:application/vnd.openxml")

    async def test_unknown_export_format_fails_before_any_request(self, drive, api):
        with pytest.raises(ValidationError, match="unknown export format"):
            await drive.export("f1", "zip")

        assert api.calls == []


class TestChanging:
    async def test_update_sends_only_what_changes(self, drive, api):
        updated = await drive.update("f1", starred=True)

        assert json.loads(api.last("PATCH")[3]) == {"starred": True}
        assert updated.starred is True

    async def test_move_swaps_parents(self, drive, api):
        await drive.move("f1", "dir")

        params = api.last("PATCH")[2]
        assert (params["addParents"], params["removeParents"]) == ("dir", "root")

    async def test_copy_and_create_folder(self, drive, api):
        assert (await drive.copy("f1", name="Backup")).name == "Backup"

        folder = await drive.create_folder("Reports", parent_id="root")

        assert isinstance(folder, Folder)
        assert json.loads(api.last("POST")[3]) == {
            "name": "Reports",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": ["root"],
        }

    async def test_trash_restore_delete(self, drive, api):
        assert await drive.trash("f1") is True
        assert json.loads(api.last("PATCH")[3]) == {"trashed": True}
        assert await drive.restore("f1") is True
        assert await drive.delete("f1") is True
        assert await drive.trash("nope") is False
        assert await drive.delete("nope") is False


class TestUploads:
    async def test_chunks_follow_the_ranges_drive_acknowledges(self, drive, api, tmp_path):
        content = bytes(range(256)) * (600 * KIB // 256)
        source = tmp_path / "data.bin"
        source.write_bytes(content)
        progress = []

        file = await drive.upload(str(source), parent_id="dir", on_progress=progress.append)

        assert file.id == "up"
        assert bytes(api.received) == content
        assert api.chunks == 3  # 256 KiB + 256 KiB + 88 KiB
        assert api.upload_meta == {"name": "data.bin", "parents": ["dir"]}
        assert api.upload_headers["x-upload-content-length"] == str(len(content))
        assert progress[-1] == 1.0
        assert progress == sorted(progress)

    async def test_a_failed_chunk_resumes_from_what_drive_kept(self, drive, api):
        content = b"x" * (3 * CHUNK)
        # the 2nd chunk dies with a 503 after Drive stored 1000 of its bytes
        api.fail_chunk = (2, 1000, 503)

        await drive.upload_content(content, "big.bin")

        assert bytes(api.received) == content
        ranges = [c[3] for c in api.calls if c[0] == "PUT"]
        assert b"" in ranges  # it asked Drive for its offset before resending

    async def test_errors_that_retrying_cannot_fix_raise(self, drive, api):
        api.fail_chunk = (1, 0, 403)

        with pytest.raises(PermissionDeniedError):
            await drive.upload_content(b"x" * CHUNK, "secret.bin")

    async def test_empty_file(self, drive, api):
        file = await drive.upload_content(b"", "empty.txt", mime_type="text/plain")

        assert file.id == "up"
        assert api.upload_headers["x-upload-content-type"] == "text/plain"

    async def test_seekable_stream_is_read_from_its_position(self, drive, api):
        stream = io.BytesIO(b"HEADER" + b"y" * (CHUNK + 10))
        stream.seek(6)

        await drive.upload_content(stream, "tail.bin")

        assert bytes(api.received) == b"y" * (CHUNK + 10)

    def test_chunk_size_must_be_a_multiple_of_256_kib(self):
        with pytest.raises(ValueError, match="256 KiB"):
            AsyncDrive(FakeCredentials(), chunk_size=1000)


class TestPermissions:
    async def test_add_list_remove_share(self, drive, api):
        permission = await drive.add_permission("f1", role="writer", email="ana@example.com")

        assert permission.role == "writer"
        assert api.last("POST")[2]["sendNotificationEmail"] == "true"
        assert [p.id for p in await drive.list_permissions("f1")] == ["p1"]
        assert await drive.remove_permission("f1", "p1") is True
        assert await drive.remove_permission("f1", "zz") is False
        assert await drive.share("nope", "ana@example.com") is False

    async def test_user_permission_needs_an_email(self, drive, api):
        with pytest.raises(ValidationError, match="email"):
            await drive.add_permission("f1", type="user")

        assert api.calls == []


class TestAsyncOnlyFiles:
    async def test_fluent_methods_raise_instead_of_doing_nothing(self, drive):
        file = await drive.get("f1")

        assert isinstance(file, File)
        with pytest.raises(TypeError, match="AsyncDrive"):
            file.trash()
        with pytest.raises(TypeError, match="AsyncDrive"):
            file.get_content()
