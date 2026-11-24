"""Several stored logins (accounts) in one token store, and the store backends behind them."""

from unittest.mock import patch

import pytest

from gsuite_core import GoogleAuth, Settings, SQLiteTokenStore, create_token_store, get_settings
from gsuite_core.storage.base import TokenStore


def token(name, scopes=("s1",)):
    return {
        "token": f"access-{name}",
        "refresh_token": f"refresh-{name}",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
        "scopes": list(scopes),
    }


@pytest.fixture
def store(tmp_path):
    return SQLiteTokenStore(str(tmp_path / "tokens.db"))


@pytest.fixture
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestAccounts:
    def test_two_accounts_do_not_share_credentials(self, store):
        store.save_token(token("work", ["a"]), "work")
        store.save_token(token("home", ["b"]), "home")

        work = GoogleAuth(token_store=store, user_id="work")
        home = GoogleAuth(token_store=store, user_id="home")

        assert work.credentials.token == "access-work"
        assert home.credentials.token == "access-home"
        assert work.accounts() == ["home", "work"]

        assert work.revoke(remote=False) is True
        assert home.accounts() == ["home"]
        assert GoogleAuth(token_store=store, user_id="home").credentials.token == "access-home"

    def test_account_comes_from_the_environment(self, store, monkeypatch, fresh_settings):
        monkeypatch.setenv("GSUITE_ACCOUNT", "work")
        assert GoogleAuth(token_store=store).user_id == "work"
        assert GoogleAuth(token_store=store, user_id="home").user_id == "home"

    def test_default_account(self, store, monkeypatch, fresh_settings):
        monkeypatch.delenv("GSUITE_ACCOUNT", raising=False)
        assert GoogleAuth(token_store=store).user_id == "default"

    @pytest.mark.parametrize("name", ["", "a b", "../x", "-x", "x" * 129])
    def test_account_name_is_validated(self, name):
        with pytest.raises(ValueError, match="account"):
            Settings(account=name, _env_file=None)

    def test_stored_scopes(self, store):
        auth = GoogleAuth(token_store=store, user_id="work", scopes=["other"])
        assert auth.stored_scopes() == []
        store.save_token(token("work", ["a", "b"]), "work")
        assert auth.stored_scopes() == ["a", "b"]

    def test_service_account_has_no_accounts(self):
        with patch("gsuite_core.auth.oauth.service_account.Credentials.from_service_account_file"):
            auth = GoogleAuth.from_service_account("sa.json")
        assert auth.accounts() == []
        assert auth.stored_scopes() == []

    def test_store_that_cannot_enumerate(self):
        class Minimal(TokenStore):
            def get_token(self, user_id="default"):
                return None

            def save_token(self, token_data, user_id="default"):
                pass

            def delete_token(self, user_id="default"):
                return False

            def exists(self, user_id="default"):
                return False

        with pytest.raises(NotImplementedError, match="Minimal"):
            GoogleAuth(token_store=Minimal()).accounts()


class TestCreateTokenStore:
    def test_sqlite_by_default(self, tmp_path):
        settings = Settings(token_db_path=str(tmp_path / "t.db"), _env_file=None)
        store = create_token_store(settings)
        assert isinstance(store, SQLiteTokenStore)
        assert store.db_path == tmp_path / "t.db"

    def test_google_auth_uses_the_configured_backend(self, monkeypatch, fresh_settings):
        pytest.importorskip("keyring")
        from gsuite_core import KeyringTokenStore

        monkeypatch.setenv("GSUITE_TOKEN_STORAGE", "keyring")
        monkeypatch.setenv("GSUITE_KEYRING_SERVICE", "my-app")
        auth = GoogleAuth()
        assert isinstance(auth.token_store, KeyringTokenStore)
        assert auth.token_store.service_name == "my-app"

    def test_secret_manager(self):
        pytest.importorskip("google.cloud.secretmanager")
        settings = Settings(
            token_storage="secretmanager",
            gcp_project_id="proj",
            token_secret_name="tokens",
            token_secret_auto_create=True,
            _env_file=None,
        )
        with patch("gsuite_core.storage.secretmanager.SecretManagerTokenStore") as cls:
            assert create_token_store(settings) is cls.return_value
        cls.assert_called_once_with(project_id="proj", secret_name="tokens", auto_create=True)

    def test_secret_manager_needs_a_project(self):
        settings = Settings(token_storage="secretmanager", _env_file=None)
        with pytest.raises(ValueError, match="GSUITE_GCP_PROJECT_ID"):
            create_token_store(settings)


class TestKeyringTokenStore:
    @pytest.fixture
    def entries(self):
        """An in-memory keyring backend, installed for the test."""
        keyring = pytest.importorskip("keyring")
        from keyring.backend import KeyringBackend
        from keyring.errors import PasswordDeleteError

        entries = {}

        class Memory(KeyringBackend):
            priority = 1

            def get_password(self, service, username):
                return entries.get((service, username))

            def set_password(self, service, username, password):
                entries[(service, username)] = password

            def delete_password(self, service, username):
                if (service, username) not in entries:
                    raise PasswordDeleteError(username)
                del entries[(service, username)]

        previous = keyring.get_keyring()
        keyring.set_keyring(Memory())
        yield entries
        keyring.set_keyring(previous)

    @pytest.fixture
    def kstore(self, entries):
        from gsuite_core import KeyringTokenStore

        return KeyringTokenStore("test-service")

    def test_round_trip(self, kstore):
        assert kstore.get_token() is None
        assert kstore.exists() is False
        assert kstore.list_users() == []

        kstore.save_token(token("default"))
        kstore.save_token(token("work"), "work")

        assert kstore.get_token() == token("default")
        assert kstore.get_token("work") == token("work")
        assert kstore.exists("work") is True
        assert kstore.list_users() == ["default", "work"]

    def test_long_token_spans_entries_within_the_windows_limit(self, kstore, entries):
        big = token("work", [f"https://www.googleapis.com/auth/scope{i}" for i in range(60)])
        kstore.save_token(big, "work")

        assert kstore.get_token("work") == big
        chunks = [v for (_, name), v in entries.items() if name.startswith("work:")]
        assert len(chunks) > 1
        assert all(len(chunk.encode("utf-16-le")) <= 2560 for chunk in chunks)

    def test_shorter_token_leaves_no_stale_entries(self, kstore, entries):
        kstore.save_token(token("work", [f"scope-{i:04d}" for i in range(300)]), "work")
        kstore.save_token(token("work"), "work")

        assert kstore.get_token("work") == token("work")
        assert sorted(name for _, name in entries) == ["__accounts__", "work:0"]

    def test_delete(self, kstore, entries):
        kstore.save_token(token("work"), "work")
        assert kstore.delete_token("work") is True
        assert kstore.delete_token("work") is False
        assert kstore.get_token("work") is None
        assert [name for _, name in entries] == ["__accounts__"]

    def test_entries_removed_by_hand(self, kstore, entries):
        kstore.save_token(token("work"), "work")
        del entries[("test-service", "work:0")]

        assert kstore.get_token("work") is None
        assert kstore.delete_token("work") is True  # tolerates the missing entry

    def test_google_auth_on_the_keyring(self, kstore):
        kstore.save_token(token("work"), "work")
        auth = GoogleAuth(token_store=kstore, user_id="work")
        assert auth.credentials.refresh_token == "refresh-work"
        assert auth.accounts() == ["work"]
