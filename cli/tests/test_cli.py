"""Smoke tests for the gsuite CLI."""

import json
from unittest.mock import Mock, patch

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
    assert {"auth", "gmail", "calendar", "sheets", "status", "serve"} <= groups


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
