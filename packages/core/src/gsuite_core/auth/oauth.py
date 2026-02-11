"""Google OAuth2 authentication."""

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gsuite_core.auth.scopes import Scopes
from gsuite_core.config import get_settings
from gsuite_core.exceptions import (
    CredentialsNotFoundError,
    TokenRefreshError,
)
from gsuite_core.storage import SQLiteTokenStore, TokenStore


class GoogleAuth:
    """
    Google OAuth2 authentication handler.

    Manages credential acquisition, refresh, and storage.
    Supports both OAuth (interactive) and Service Account (server-to-server).

    Example:
        # OAuth (interactive)
        auth = GoogleAuth()
        auth.authenticate()  # Opens browser

        # Service Account
        auth = GoogleAuth.from_service_account("service-account.json")

        # Use credentials
        service = build("gmail", "v1", credentials=auth.credentials)
    """

    def __init__(
        self,
        token_store: TokenStore | None = None,
        credentials_file: str | None = None,
        scopes: list[str] | None = None,
        user_id: str = "default",
    ):
        """
        Initialize OAuth authenticator.

        Args:
            token_store: Storage backend for tokens (default: SQLite)
            credentials_file: Path to OAuth credentials JSON
            scopes: OAuth scopes to request (default: Gmail + Calendar)
            user_id: User identifier for multi-user setups
        """
        settings = get_settings()

        self.token_store = token_store or SQLiteTokenStore(settings.token_db_path)
        self.credentials_file = Path(credentials_file or settings.credentials_file)
        self.scopes = scopes or Scopes.default()
        self.user_id = user_id
        self._credentials: Credentials | None = None

    @classmethod
    def from_service_account(
        cls,
        service_account_file: str,
        scopes: list[str] | None = None,
        subject: str | None = None,
    ) -> "GoogleAuth":
        """
        Create authenticator from service account.

        Args:
            service_account_file: Path to service account JSON
            scopes: OAuth scopes
            subject: Email to impersonate (for domain-wide delegation)

        Returns:
            GoogleAuth instance with service account credentials
        """
        instance = cls.__new__(cls)
        instance.token_store = None
        instance.credentials_file = Path(service_account_file)
        instance.scopes = scopes or Scopes.default()
        instance.user_id = "service_account"

        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=instance.scopes,
        )

        if subject:
            creds = creds.with_subject(subject)

        instance._credentials = creds
        return instance

    @property
    def credentials(self) -> Credentials | None:
        """Get current credentials, loading from store if needed."""
        if self._credentials is None:
            self._load_credentials()
        return self._credentials

    def _load_credentials(self) -> None:
        """Load credentials from token store."""
        if self.token_store is None:
            return

        token_data = self.token_store.get_token(self.user_id)

        if token_data:
            # Use Credentials constructor directly to ensure scopes are set correctly.
            # from_authorized_user_info() has issues with scope handling that cause
            # credentials.valid to be False even with valid tokens.
            self._credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes") or self.scopes,
            )

    def _save_credentials(self) -> None:
        """Save current credentials to token store."""
        if self._credentials and self.token_store:
            token_data = {
                "token": self._credentials.token,
                "refresh_token": self._credentials.refresh_token,
                "token_uri": self._credentials.token_uri,
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
                "scopes": list(self._credentials.scopes or self.scopes),
            }
            self.token_store.save_token(token_data, self.user_id)

    def is_authenticated(self) -> bool:
        """Check if we have valid credentials."""
        creds = self.credentials
        return creds is not None and creds.valid

    def needs_refresh(self) -> bool:
        """Check if credentials need refresh."""
        creds = self.credentials
        if creds is None:
            return False
        return creds.expired and creds.refresh_token is not None

    def refresh(self) -> bool:
        """
        Refresh expired credentials.

        Returns:
            True if refresh succeeded

        Raises:
            TokenRefreshError: If refresh fails
        """
        if not self.needs_refresh():
            return False

        try:
            self._credentials.refresh(Request())
            self._save_credentials()
            return True
        except RefreshError as e:
            raise TokenRefreshError(cause=e) from e
        except Exception as e:
            raise TokenRefreshError(cause=e) from e

    def authenticate(self, force: bool = False) -> Credentials:
        """
        Get valid credentials, running OAuth flow if needed.

        Args:
            force: Force new authentication even if credentials exist

        Returns:
            Valid Google credentials

        Raises:
            FileNotFoundError: If credentials file doesn't exist
        """
        if not force:
            if self.is_authenticated():
                return self._credentials

            if self.needs_refresh() and self.refresh():
                return self._credentials

        if not self.credentials_file.exists():
            raise CredentialsNotFoundError(str(self.credentials_file))

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_file),
            self.scopes,
        )

        self._credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )

        self._save_credentials()
        return self._credentials

    def revoke(self) -> bool:
        """
        Revoke and delete stored credentials.

        Returns:
            True if credentials were deleted
        """
        self._credentials = None
        if self.token_store:
            return self.token_store.delete_token(self.user_id)
        return False

    def export_token(self) -> dict | None:
        """
        Export token data for external storage.

        Returns:
            Token data dict or None if not authenticated
        """
        if self._credentials:
            return {
                "token": self._credentials.token,
                "refresh_token": self._credentials.refresh_token,
                "token_uri": self._credentials.token_uri,
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
                "scopes": list(self._credentials.scopes or self.scopes),
            }
        return None

    def get_user_email(self) -> str | None:
        """
        Get authenticated user's email.

        Returns:
            Email address or None
        """
        if not self.is_authenticated():
            return None

        from googleapiclient.discovery import build

        try:
            service = build("oauth2", "v2", credentials=self._credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get("email")
        except Exception:
            return None
