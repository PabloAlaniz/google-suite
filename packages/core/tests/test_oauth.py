"""Tests for Google OAuth authentication."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials

from gsuite_core.auth.oauth import GoogleAuth
from gsuite_core.auth.scopes import Scopes
from gsuite_core.exceptions import CredentialsNotFoundError, TokenRefreshError
from gsuite_core.storage import SQLiteTokenStore


class TestGoogleAuth:
    """Tests for GoogleAuth class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def temp_credentials_file(self):
        """Create a temporary credentials file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w") as f:
            f.write('{"installed": {"client_id": "test", "client_secret": "secret"}}')
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def token_store(self, temp_db):
        """Create a token store with temp database."""
        return SQLiteTokenStore(db_path=temp_db)

    @pytest.fixture
    def mock_credentials(self):
        """Create mock credentials."""
        creds = Mock(spec=Credentials)
        creds.valid = True
        creds.expired = False
        creds.refresh_token = "refresh_token_123"
        creds.token = "access_token_123"
        creds.token_uri = "https://oauth2.googleapis.com/token"
        creds.client_id = "client_id_123"
        creds.client_secret = "client_secret_123"
        creds.scopes = Scopes.default()
        return creds

    @pytest.fixture
    def auth_instance(self, token_store, temp_credentials_file):
        """Create a GoogleAuth instance."""
        return GoogleAuth(
            token_store=token_store,
            credentials_file=temp_credentials_file,
            scopes=Scopes.default(),
            user_id="test_user",
        )

    def test_init(self, token_store, temp_credentials_file):
        """Test GoogleAuth initialization."""
        auth = GoogleAuth(
            token_store=token_store,
            credentials_file=temp_credentials_file,
            scopes=Scopes.default(),
            user_id="test_user",
        )

        assert auth.token_store == token_store
        assert auth.credentials_file == Path(temp_credentials_file)
        assert auth.scopes == Scopes.default()
        assert auth.user_id == "test_user"
        assert auth._credentials is None

    def test_init_defaults(self):
        """Test GoogleAuth initialization with defaults."""
        with patch("gsuite_core.auth.oauth.get_settings") as mock_settings:
            settings = Mock()
            settings.token_db_path = "default.db"
            settings.credentials_file = "credentials.json"
            mock_settings.return_value = settings

            auth = GoogleAuth()

            assert isinstance(auth.token_store, SQLiteTokenStore)
            assert auth.credentials_file == Path("credentials.json")
            assert auth.scopes == Scopes.default()
            assert auth.user_id == "default"

    @patch("gsuite_core.auth.oauth.service_account.Credentials.from_service_account_file")
    def test_from_service_account(self, mock_from_file, temp_credentials_file):
        """Test creating GoogleAuth from service account."""
        mock_creds = Mock(spec=service_account.Credentials)
        mock_from_file.return_value = mock_creds

        auth = GoogleAuth.from_service_account(
            temp_credentials_file,
            scopes=Scopes.gmail(),
        )

        assert auth.token_store is None
        assert auth.credentials_file == Path(temp_credentials_file)
        assert auth.scopes == Scopes.gmail()
        assert auth.user_id == "service_account"
        assert auth._credentials == mock_creds
        mock_from_file.assert_called_once_with(
            temp_credentials_file,
            scopes=Scopes.gmail(),
        )

    @patch("gsuite_core.auth.oauth.service_account.Credentials.from_service_account_file")
    def test_from_service_account_with_subject(self, mock_from_file, temp_credentials_file):
        """Test creating GoogleAuth from service account with subject impersonation."""
        mock_creds = Mock(spec=service_account.Credentials)
        mock_creds_with_subject = Mock(spec=service_account.Credentials)
        mock_creds.with_subject.return_value = mock_creds_with_subject
        mock_from_file.return_value = mock_creds

        auth = GoogleAuth.from_service_account(
            temp_credentials_file,
            subject="user@example.com",
        )

        mock_creds.with_subject.assert_called_once_with("user@example.com")
        assert auth._credentials == mock_creds_with_subject

    def test_credentials_property_loads_from_store(self, auth_instance, token_store):
        """Test that credentials property loads from store if not in memory."""
        token_data = {
            "token": "access_token_123",
            "refresh_token": "refresh_token_123",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id_123",
            "client_secret": "client_secret_123",
            "scopes": Scopes.default(),
        }
        token_store.save_token(token_data, user_id="test_user")

        with patch(
            "gsuite_core.auth.oauth.Credentials.from_authorized_user_info"
        ) as mock_from_info:
            mock_creds = Mock(spec=Credentials)
            mock_from_info.return_value = mock_creds

            creds = auth_instance.credentials

            mock_from_info.assert_called_once_with(token_data, Scopes.default())
            assert creds == mock_creds

    def test_credentials_property_returns_cached(self, auth_instance, mock_credentials):
        """Test that credentials property returns cached credentials."""
        auth_instance._credentials = mock_credentials

        creds = auth_instance.credentials

        assert creds == mock_credentials

    def test_load_credentials_no_token_store(self):
        """Test loading credentials when token_store is None."""
        auth = GoogleAuth.__new__(GoogleAuth)
        auth.token_store = None
        auth._credentials = None

        auth._load_credentials()

        assert auth._credentials is None

    def test_save_credentials(self, auth_instance, mock_credentials):
        """Test saving credentials to token store."""
        auth_instance._credentials = mock_credentials

        auth_instance._save_credentials()

        saved_token = auth_instance.token_store.get_token("test_user")
        assert saved_token is not None
        assert saved_token["token"] == "access_token_123"
        assert saved_token["refresh_token"] == "refresh_token_123"

    def test_save_credentials_no_credentials(self, auth_instance):
        """Test saving when no credentials exist."""
        auth_instance._credentials = None

        auth_instance._save_credentials()

        saved_token = auth_instance.token_store.get_token("test_user")
        assert saved_token is None

    def test_save_credentials_no_token_store(self, mock_credentials):
        """Test saving when token_store is None."""
        auth = GoogleAuth.__new__(GoogleAuth)
        auth.token_store = None
        auth._credentials = mock_credentials

        # Should not raise an error
        auth._save_credentials()

    def test_is_authenticated_valid_credentials(self, auth_instance, mock_credentials):
        """Test is_authenticated with valid credentials."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = True

        assert auth_instance.is_authenticated() is True

    def test_is_authenticated_invalid_credentials(self, auth_instance, mock_credentials):
        """Test is_authenticated with invalid credentials."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = False

        assert auth_instance.is_authenticated() is False

    def test_is_authenticated_no_credentials(self, auth_instance):
        """Test is_authenticated with no credentials."""
        auth_instance._credentials = None

        assert auth_instance.is_authenticated() is False

    def test_needs_refresh_expired_with_refresh_token(self, auth_instance, mock_credentials):
        """Test needs_refresh with expired credentials that have refresh token."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_token_123"

        assert auth_instance.needs_refresh() is True

    def test_needs_refresh_expired_no_refresh_token(self, auth_instance, mock_credentials):
        """Test needs_refresh with expired credentials but no refresh token."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = True
        mock_credentials.refresh_token = None

        assert auth_instance.needs_refresh() is False

    def test_needs_refresh_not_expired(self, auth_instance, mock_credentials):
        """Test needs_refresh with valid credentials."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = False

        assert auth_instance.needs_refresh() is False

    def test_needs_refresh_no_credentials(self, auth_instance):
        """Test needs_refresh with no credentials."""
        auth_instance._credentials = None

        assert auth_instance.needs_refresh() is False

    @patch("gsuite_core.auth.oauth.Request")
    def test_refresh_success(self, mock_request_class, auth_instance, mock_credentials):
        """Test successful token refresh."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_token_123"

        mock_request = Mock()
        mock_request_class.return_value = mock_request

        result = auth_instance.refresh()

        assert result is True
        mock_credentials.refresh.assert_called_once_with(mock_request)
        # Verify credentials were saved
        saved_token = auth_instance.token_store.get_token("test_user")
        assert saved_token is not None

    def test_refresh_not_needed(self, auth_instance, mock_credentials):
        """Test refresh when not needed."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = False

        result = auth_instance.refresh()

        assert result is False
        mock_credentials.refresh.assert_not_called()

    @patch("gsuite_core.auth.oauth.Request")
    def test_refresh_raises_token_refresh_error(
        self, mock_request_class, auth_instance, mock_credentials
    ):
        """Test refresh raises TokenRefreshError on failure."""
        auth_instance._credentials = mock_credentials
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_token_123"
        mock_credentials.refresh.side_effect = RefreshError("Refresh failed")

        with pytest.raises(TokenRefreshError):
            auth_instance.refresh()

    @patch("gsuite_core.auth.oauth.InstalledAppFlow")
    def test_authenticate_already_valid(self, mock_flow, auth_instance, mock_credentials):
        """Test authenticate when already authenticated."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = True

        result = auth_instance.authenticate()

        assert result == mock_credentials
        mock_flow.assert_not_called()

    @patch("gsuite_core.auth.oauth.Request")
    @patch("gsuite_core.auth.oauth.InstalledAppFlow")
    def test_authenticate_needs_refresh(
        self, mock_flow, mock_request_class, auth_instance, mock_credentials
    ):
        """Test authenticate when credentials need refresh."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.refresh_token = "refresh_token_123"

        mock_request = Mock()
        mock_request_class.return_value = mock_request

        # After refresh, credentials become valid
        def make_valid(*args):
            mock_credentials.valid = True

        mock_credentials.refresh.side_effect = make_valid

        result = auth_instance.authenticate()

        assert result == mock_credentials
        mock_credentials.refresh.assert_called_once_with(mock_request)
        mock_flow.assert_not_called()

    @patch("gsuite_core.auth.oauth.InstalledAppFlow")
    def test_authenticate_runs_oauth_flow(self, mock_flow, auth_instance, mock_credentials):
        """Test authenticate runs OAuth flow when needed."""
        auth_instance._credentials = None

        mock_flow_instance = Mock()
        mock_flow.from_client_secrets_file.return_value = mock_flow_instance
        mock_flow_instance.run_local_server.return_value = mock_credentials

        result = auth_instance.authenticate()

        assert result == mock_credentials
        mock_flow.from_client_secrets_file.assert_called_once_with(
            str(auth_instance.credentials_file),
            Scopes.default(),
        )
        mock_flow_instance.run_local_server.assert_called_once_with(
            port=0,
            prompt="consent",
            access_type="offline",
        )
        # Verify credentials were saved
        saved_token = auth_instance.token_store.get_token("test_user")
        assert saved_token is not None

    def test_authenticate_force(self, auth_instance, mock_credentials):
        """Test authenticate with force=True."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = True

        with patch("gsuite_core.auth.oauth.InstalledAppFlow") as mock_flow:
            new_creds = Mock(spec=Credentials)
            new_creds.token = "new_token"
            new_creds.refresh_token = "new_refresh"
            new_creds.token_uri = "https://oauth2.googleapis.com/token"
            new_creds.client_id = "client_id"
            new_creds.client_secret = "client_secret"
            new_creds.scopes = Scopes.default()

            mock_flow_instance = Mock()
            mock_flow.from_client_secrets_file.return_value = mock_flow_instance
            mock_flow_instance.run_local_server.return_value = new_creds

            result = auth_instance.authenticate(force=True)

            assert result == new_creds
            mock_flow_instance.run_local_server.assert_called_once()

    def test_authenticate_missing_credentials_file(self, auth_instance):
        """Test authenticate raises error when credentials file doesn't exist."""
        auth_instance._credentials = None
        auth_instance.credentials_file = Path("/nonexistent/credentials.json")

        with pytest.raises(CredentialsNotFoundError):
            auth_instance.authenticate()

    def test_revoke(self, auth_instance, mock_credentials, token_store):
        """Test revoking credentials."""
        auth_instance._credentials = mock_credentials
        token_store.save_token({"token": "test"}, user_id="test_user")

        result = auth_instance.revoke()

        assert result is True
        assert auth_instance._credentials is None
        assert token_store.get_token("test_user") is None

    def test_revoke_no_token_store(self, mock_credentials):
        """Test revoke when token_store is None."""
        auth = GoogleAuth.__new__(GoogleAuth)
        auth.token_store = None
        auth._credentials = mock_credentials

        result = auth.revoke()

        assert result is False
        assert auth._credentials is None

    def test_export_token(self, auth_instance, mock_credentials):
        """Test exporting token data."""
        auth_instance._credentials = mock_credentials

        token_data = auth_instance.export_token()

        assert token_data is not None
        assert token_data["token"] == "access_token_123"
        assert token_data["refresh_token"] == "refresh_token_123"
        assert token_data["token_uri"] == "https://oauth2.googleapis.com/token"
        assert token_data["client_id"] == "client_id_123"
        assert token_data["client_secret"] == "client_secret_123"
        assert token_data["scopes"] == Scopes.default()

    def test_export_token_no_credentials(self, auth_instance):
        """Test export_token with no credentials."""
        auth_instance._credentials = None

        token_data = auth_instance.export_token()

        assert token_data is None

    @patch("googleapiclient.discovery.build")
    def test_get_user_email(self, mock_build, auth_instance, mock_credentials):
        """Test getting user email."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = True

        mock_service = Mock()
        mock_userinfo = Mock()
        mock_userinfo.get.return_value.execute.return_value = {"email": "user@example.com"}
        mock_service.userinfo.return_value = mock_userinfo
        mock_build.return_value = mock_service

        email = auth_instance.get_user_email()

        assert email == "user@example.com"
        mock_build.assert_called_once_with("oauth2", "v2", credentials=mock_credentials)

    def test_get_user_email_not_authenticated(self, auth_instance):
        """Test get_user_email when not authenticated."""
        auth_instance._credentials = None

        email = auth_instance.get_user_email()

        assert email is None

    @patch("googleapiclient.discovery.build")
    def test_get_user_email_api_error(self, mock_build, auth_instance, mock_credentials):
        """Test get_user_email when API call fails."""
        auth_instance._credentials = mock_credentials
        mock_credentials.valid = True
        mock_build.side_effect = Exception("API error")

        email = auth_instance.get_user_email()

        assert email is None
