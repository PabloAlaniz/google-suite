"""Smoke tests for the gsuite CLI."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from gsuite_cli.main import app

runner = CliRunner()


def _command_paths(command, prefix=()):
    """Yield the argv path of every command and sub-command in the app."""
    yield prefix
    for name, sub in getattr(command, "commands", {}).items():
        yield from _command_paths(sub, (*prefix, name))


ALL_COMMANDS = list(_command_paths(get_command(app)))


def test_expected_groups_registered():
    groups = {path[0] for path in ALL_COMMANDS if path}
    assert {"auth", "gmail", "calendar", "drive", "sheets", "status", "serve"} <= groups


@pytest.mark.parametrize("path", ALL_COMMANDS, ids=lambda p: " ".join(p) or "gsuite")
def test_help(path):
    result = runner.invoke(app, [*path, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


def _unauthenticated_auth():
    auth = Mock()
    auth.is_authenticated.return_value = False
    auth.needs_refresh.return_value = False
    return auth


def test_auth_status_not_authenticated():
    with patch("gsuite_cli.auth.GoogleAuth", return_value=_unauthenticated_auth()):
        result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "Not authenticated" in result.output


def test_gmail_list_requires_auth():
    with patch("gsuite_cli.gmail.GoogleAuth", return_value=_unauthenticated_auth()):
        result = runner.invoke(app, ["gmail", "list"])

    assert result.exit_code == 1
    assert "gsuite auth login" in result.output


def test_gmail_list_json_builds_query():
    auth = Mock()
    auth.is_authenticated.return_value = True
    message = Mock(
        id="msg_1",
        subject="Hello",
        sender="a@example.com",
        date=None,
        is_unread=True,
        is_starred=False,
    )
    gmail = Mock()
    gmail.get_messages.return_value = [message]

    with (
        patch("gsuite_cli.gmail.GoogleAuth", return_value=auth),
        patch("gsuite_cli.gmail.Gmail", return_value=gmail),
    ):
        result = runner.invoke(
            app, ["gmail", "list", "--unread", "--from", "a@example.com", "-o", "json"]
        )

    assert result.exit_code == 0, result.output
    gmail.get_messages.assert_called_once_with(query="is:unread from:a@example.com", max_results=20)
    assert json.loads(result.output) == [
        {
            "id": "msg_1",
            "subject": "Hello",
            "from": "a@example.com",
            "date": None,
            "is_unread": True,
            "is_starred": False,
        }
    ]


def test_sdk_errors_are_reported_without_traceback(capsys):
    from gsuite_cli.main import main
    from gsuite_core.exceptions import RateLimitError

    with (
        patch("gsuite_cli.main.app", side_effect=RateLimitError("gmail", retry_after=30)),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "Rate limit exceeded" in capsys.readouterr().out


class TestSheetsCli:
    @pytest.fixture
    def client(self):
        client = MagicMock()
        with patch("gsuite_cli.sheets.get_sheets", return_value=client):
            yield client

    def _ws(self, client, values):
        ws = MagicMock(title="Sheet1", id=0)
        ws.get.return_value = values
        client.open.return_value.sheet1 = ws
        client.open.return_value.worksheet.return_value = ws
        return ws

    def test_read_table(self, client):
        # Used to crash: the `range` parameter shadowed the builtin range()
        self._ws(client, [["a", "b"], ["1", "2", "3"]])

        result = runner.invoke(app, ["sheets", "read", "Budget", "-r", "A1:C2"])

        assert result.exit_code == 0, result.output
        assert "C" in result.output and "3" in result.output

    def test_read_csv(self, client):
        self._ws(client, [["a", "b,c"]])
        result = runner.invoke(app, ["sheets", "read", "Budget", "-o", "csv"])
        assert result.output.strip() == 'a,"b,c"'

    def test_write_raw(self, client):
        ws = self._ws(client, [])
        runner.invoke(app, ["sheets", "write", "Budget", "-c", "A1", "-v", "=1+1", "--raw"])
        ws.update.assert_called_once_with("A1", [["=1+1"]], value_input="RAW")

    def test_missing_worksheet(self, client):
        client.open.return_value.worksheet.return_value = None
        result = runner.invoke(
            app, ["sheets", "write", "Budget", "-c", "A1", "-v", "x", "-s", "Nope"]
        )
        assert result.exit_code == 1
        assert "Worksheet not found" in result.output

    def test_replace_all_sheets(self, client):
        doc = client.open.return_value
        doc._sheets.find_replace.return_value = 2

        result = runner.invoke(app, ["sheets", "replace", "Budget", "old", "new", "--regex"])

        assert "Replaced 2" in result.output
        assert doc._sheets.find_replace.call_args.kwargs["sheet_id"] is None

    def test_freeze_requires_something(self, client):
        assert runner.invoke(app, ["sheets", "freeze", "Budget"]).exit_code == 2

    def test_delete_tab_confirms(self, client):
        self._ws(client, [])
        result = runner.invoke(app, ["sheets", "delete-tab", "Budget", "Sheet1"], input="n\n")
        assert result.exit_code == 1
        client.open.return_value.del_worksheet.assert_not_called()


class TestGmailAndCalendarCli:
    @pytest.fixture
    def gmail(self):
        client = MagicMock()
        with patch("gsuite_cli.gmail.get_gmail", return_value=client):
            yield client

    @pytest.fixture
    def cal(self):
        client = MagicMock()
        client.create_event.return_value = MagicMock(
            id="e1", summary="Sync", html_link=None, meet_link="https://meet.google.com/x"
        )
        with patch("gsuite_cli.calendar.get_calendar", return_value=client):
            yield client

    def test_send_with_attachment(self, gmail, tmp_path):
        report = tmp_path / "r.pdf"
        report.write_bytes(b"%PDF")

        result = runner.invoke(
            app, ["gmail", "send", "-t", "a@x.com", "-s", "R", "-b", "see", "-a", str(report)]
        )

        assert result.exit_code == 0, result.output
        assert gmail.send.call_args.kwargs["attachments"] == [report]

    def test_reply_all(self, gmail):
        result = runner.invoke(app, ["gmail", "reply", "m1", "-b", "thanks", "--all"])
        assert result.exit_code == 0, result.output
        assert gmail.reply.call_args.kwargs["reply_all"] is True

    def test_reply_missing_message(self, gmail):
        gmail.get_message.return_value = None
        assert runner.invoke(app, ["gmail", "reply", "nope", "-b", "x"]).exit_code == 1

    def test_calendar_create_with_meet(self, cal):
        result = runner.invoke(
            app,
            [
                "calendar",
                "create",
                "Sync",
                "-s",
                "2026-03-01 10:00",
                "--meet",
                "-a",
                "b@x.com",
                "--repeat",
                "FREQ=WEEKLY",
                "--notify",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "meet.google.com/x" in result.output
        kwargs = cal.create_event.call_args.kwargs
        assert kwargs["recurrence"] == ["RRULE:FREQ=WEEKLY"]
        assert kwargs["send_updates"] == "all"
        assert kwargs["attendees"] == ["b@x.com"]


class TestGmailActionsCli:
    @pytest.fixture
    def gmail(self):
        client = MagicMock()
        with patch("gsuite_cli.gmail.get_gmail", return_value=client):
            yield client

    def test_mark(self, gmail):
        assert runner.invoke(app, ["gmail", "mark", "m1", "--unread", "--star"]).exit_code == 0
        gmail.batch_modify.assert_called_once_with(
            ["m1"], add_labels=["UNREAD", "STARRED"], remove_labels=[]
        )

    @pytest.mark.parametrize("flags", [[], ["--read", "--unread"]])
    def test_mark_needs_one_choice(self, gmail, flags):
        assert runner.invoke(app, ["gmail", "mark", "m1", *flags]).exit_code == 2

    def test_archive_and_trash(self, gmail):
        assert runner.invoke(app, ["gmail", "archive", "m1"]).exit_code == 0
        gmail.batch_modify.assert_called_once_with(["m1"], remove_labels=["INBOX"])
        assert runner.invoke(app, ["gmail", "trash", "m1"]).exit_code == 0
        gmail.get_message.return_value.trash.assert_called_once_with()


def test_calendar_quick():
    from datetime import datetime

    client = MagicMock()
    client.quick_add.return_value = MagicMock(summary="Lunch", start=datetime(2026, 3, 2, 13))
    with patch("gsuite_cli.calendar.get_calendar", return_value=client):
        result = runner.invoke(app, ["calendar", "quick", "Lunch tomorrow at 1pm"])
    assert "Lunch — 2026-03-02 13:00" in result.output
