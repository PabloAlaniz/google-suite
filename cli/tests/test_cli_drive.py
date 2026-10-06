"""Drive CLI commands with a mocked Drive client."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsuite_cli.main import app
from gsuite_drive import File, Permission

runner = CliRunner()


@pytest.fixture
def drive():
    client = MagicMock()
    with patch("gsuite_cli.drive.get_drive", return_value=client):
        yield client


def _file(**overrides):
    fields = {"id": "f1", "name": "a.txt", "mime_type": "text/plain", "size": 2048}
    fields.update(overrides)
    return File(**fields)


def test_ls_json(drive):
    drive.list_files.return_value = [_file(modified_time=datetime(2026, 1, 1, tzinfo=UTC))]

    result = runner.invoke(app, ["drive", "ls", "dir", "--name", "Pablo's", "-o", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["modified_time"] == "2026-01-01T00:00:00+00:00"
    kwargs = drive.list_files.call_args.kwargs
    assert kwargs["parent_id"] == "dir"
    assert kwargs["query"] == "name contains 'Pablo\\'s'"


def test_ls_table(drive):
    drive.list_files.return_value = [
        _file(),
        _file(id="d", name="docs", mime_type="application/vnd.google-apps.folder"),
    ]

    result = runner.invoke(app, ["drive", "ls"])

    assert "docs/" in result.output
    assert "2.0 KB" in result.output


def test_long_values_stay_valid_json(drive):
    # Regression: rich wrapped long lines inside JSON strings
    drive.list_files.return_value = [_file(name="x" * 300)]

    result = runner.invoke(app, ["drive", "ls", "-o", "json"])

    assert json.loads(result.output)[0]["name"] == "x" * 300


def test_info(drive):
    drive.get.return_value = _file()
    drive.list_permissions.return_value = [
        Permission(id="p", type="user", role="writer", email_address="b@x.com")
    ]

    result = runner.invoke(app, ["drive", "info", "f1"])

    assert "writer" in result.output and "b@x.com" in result.output


def test_missing_file(drive):
    drive.get.return_value = None
    result = runner.invoke(app, ["drive", "download", "nope"])
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_download_export(drive, tmp_path):
    file = MagicMock(spec=File)
    file.name = "Plan"
    file.download.return_value = str(tmp_path / "Plan.pdf")
    drive.get.return_value = file

    result = runner.invoke(app, ["drive", "download", "d1", "--export", "pdf"])

    assert result.exit_code == 0, result.output
    file.download.assert_called_once_with(None, export_format="pdf")


def test_upload_reports_progress(drive, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hi")

    def upload(local, name, parent_id, on_progress):
        on_progress(0.5)
        on_progress(1.0)
        return _file(id="up", name="notes.txt")

    drive.upload.side_effect = upload

    result = runner.invoke(app, ["drive", "upload", str(path), "--to", "dir"])

    assert result.exit_code == 0, result.output
    assert "Uploaded" in result.output


@pytest.mark.parametrize("command", ["delete", "rm"])
def test_delete_trashes_by_default(drive, command):
    drive.trash.return_value = True
    result = runner.invoke(app, ["drive", command, "f1"])
    assert result.exit_code == 0
    drive.delete.assert_not_called()


def test_permanent_rm_asks_first(drive):
    result = runner.invoke(app, ["drive", "rm", "f1", "--permanent"], input="n\n")
    assert result.exit_code == 1
    drive.delete.assert_not_called()


def test_permanent_rm_with_yes(drive):
    drive.delete.return_value = True
    assert runner.invoke(app, ["drive", "rm", "f1", "--permanent", "-y"]).exit_code == 0
    drive.delete.assert_called_once_with("f1")


def test_share_needs_target(drive):
    assert runner.invoke(app, ["drive", "share", "f1"]).exit_code == 2


def test_share_anyone(drive):
    drive.add_permission.return_value = Permission(id="a", type="anyone", role="reader")

    result = runner.invoke(app, ["drive", "share", "f1", "--anyone"])

    assert "anyone with the link" in result.output
    assert drive.add_permission.call_args.kwargs["type"] == "anyone"


def test_mkdir_and_mv(drive):
    drive.create_folder.return_value = _file(id="d", name="D")
    drive.move.return_value = _file()

    assert runner.invoke(app, ["drive", "mkdir", "D", "--in", "root"]).exit_code == 0
    assert runner.invoke(app, ["drive", "mv", "f1", "d"]).exit_code == 0
    drive.move.assert_called_once_with("f1", "d")
