"""`gsuite --account`, `gsuite auth list` and `gsuite auth login --add`."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsuite_cli.main import app
from gsuite_core import GoogleAuth, SQLiteTokenStore, get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """A token store of its own, and no account left behind in the environment."""
    monkeypatch.setenv("GSUITE_TOKEN_DB_PATH", str(tmp_path / "tokens.db"))
    monkeypatch.setenv("GSUITE_TOKEN_STORAGE", "sqlite")
    monkeypatch.setenv("GSUITE_ACCOUNT", "default")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(tmp_path):
    store = SQLiteTokenStore(str(tmp_path / "tokens.db"))
    base = "https://www.googleapis.com/auth/"
    store.save_token({"token": "d", "scopes": [base + "gmail.modify"]})
    store.save_token({"token": "w", "scopes": [base + "drive", base + "tasks"]}, "work")
    return store


class TestAccountOption:
    def test_selects_the_account_for_any_command(self, store):
        seen = []

        def fake_auth(*args, **kwargs):
            auth = GoogleAuth(*args, **kwargs)
            seen.append(auth.user_id)
            unauthenticated = MagicMock(user_id=auth.user_id)
            unauthenticated.is_authenticated.return_value = False
            unauthenticated.needs_refresh.return_value = False
            return unauthenticated

        with patch("gsuite_cli.auth.GoogleAuth", side_effect=fake_auth):
            assert runner.invoke(app, ["--account", "work", "auth", "status"]).exit_code == 0
            assert runner.invoke(app, ["-a", "ana@example.com", "auth", "status"]).exit_code == 0
        assert seen == ["work", "ana@example.com"]

    def test_default_without_the_option(self, store):
        result = runner.invoke(app, ["auth", "list", "--json"])
        active = [row["account"] for row in json.loads(result.output) if row["active"]]
        assert active == ["default"]

    @pytest.mark.parametrize("name", ["a b", "../x", "-x"])
    def test_invalid_name(self, name):
        result = runner.invoke(app, ["--account", name, "auth", "status"])
        assert result.exit_code == 1
        assert "Invalid account name" in result.output


class TestAuthList:
    def test_table(self, store):
        result = runner.invoke(app, ["--account", "work", "auth", "list"])
        assert result.exit_code == 0, result.output
        assert "default" in result.output
        assert "gmail.modify" in result.output
        assert "drive, tasks" in result.output

    def test_json(self, store):
        result = runner.invoke(app, ["--account", "work", "auth", "list", "--json"])
        rows = json.loads(result.output)
        assert [(row["account"], row["active"]) for row in rows] == [
            ("default", False),
            ("work", True),
        ]
        assert rows[1]["scopes"][0].endswith("/drive")

    def test_empty(self):
        result = runner.invoke(app, ["auth", "list"])
        assert result.exit_code == 0
        assert "No stored logins" in result.output

    def test_store_that_cannot_list(self):
        auth = MagicMock()
        auth.accounts.side_effect = NotImplementedError("MyStore cannot list its accounts")
        with patch("gsuite_cli.auth.GoogleAuth", return_value=auth):
            result = runner.invoke(app, ["auth", "list"])
        assert result.exit_code == 1
        assert "cannot list" in result.output


class TestLoginAdd:
    def _login(self, args):
        """Run `auth login`, returning the result and the scopes each flow asked for."""
        asked = []

        def authenticate(self, force=False):
            asked.append((self.user_id, list(self.scopes), force))
            return MagicMock(scopes=self.scopes)

        with patch.object(GoogleAuth, "authenticate", authenticate):
            return runner.invoke(app, args), asked

    def test_adds_to_the_stored_scopes(self, store):
        from gsuite_core import Scopes

        result, asked = self._login(["-a", "work", "auth", "login", "--add", "-s", "contacts"])

        assert result.exit_code == 0, result.output
        [(account, scopes, force)] = asked
        assert account == "work"
        assert scopes == [*GoogleAuth(user_id="work").stored_scopes(), *Scopes.contacts()]
        assert force is True

    def test_nothing_new_skips_the_consent(self, store):
        result, asked = self._login(["-a", "work", "auth", "login", "--add", "-s", "tasks"])

        assert result.exit_code == 0
        assert "already has those scopes" in result.output
        assert asked == []

    def test_first_login_of_an_account(self, store):
        from gsuite_core import Scopes

        result, asked = self._login(["-a", "new", "auth", "login", "--add", "-s", "tasks"])

        assert result.exit_code == 0, result.output
        assert asked == [("new", Scopes.tasks(), True)]

    def test_without_add_scopes_are_replaced(self, store):
        from gsuite_core import Scopes

        _, asked = self._login(["-a", "work", "auth", "login", "--force", "-s", "contacts"])
        assert asked == [("work", Scopes.contacts(), True)]
