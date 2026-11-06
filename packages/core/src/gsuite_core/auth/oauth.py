"""Google OAuth2 authentication."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httplib2
from google.auth.exceptions import GoogleAuthError, RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

from gsuite_core.auth.scopes import Scopes
from gsuite_core.config import get_settings
from gsuite_core.exceptions import (
    AuthenticationError,
    CredentialsNotFoundError,
    TokenRefreshError,
)
from gsuite_core.storage import SQLiteTokenStore, TokenStore

# Desktop OAuth clients accept any localhost redirect. Without a server
# listening there, the browser shows an error page whose URL carries the code:
# the user pastes that URL (or just the code) back.
DEFAULT_REDIRECT_URI = "http://localhost"


@dataclass(frozen=True)
class AuthorizationRequest:
    """A login started with ``GoogleAuth.start_authorization``.

    Keep it (``to_dict()`` / ``from_dict()``) until the user comes back with
    the code: a web server may finish the login in another request, or another
    process. It holds the PKCE verifier, so store it like a short-lived secret.
    """

    url: str
    state: str
    code_verifier: str
    redirect_uri: str

    def to_dict(self) -> dict[str, str]:
        """The fields as a dict, e.g. to keep in a session or a database row."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "AuthorizationRequest":
        """Rebuild a request saved with ``to_dict()``."""
        return cls(**{key: data[key] for key in ("url", "state", "code_verifier", "redirect_uri")})


def _code_from(code_or_url: str, expected_state: str) -> str:
    """The code from what the user pasted: the code itself or the redirect URL."""
    value = code_or_url.strip()
    if "://" not in value:
        return value
    query = parse_qs(urlparse(value).query)
    if "error" in query:
        raise AuthenticationError(f"Google declined the login: {query['error'][0]}")
    if query.get("state", [expected_state])[0] != expected_state:
        raise AuthenticationError("This URL belongs to another login attempt; start again")
    try:
        return query["code"][0]
    except KeyError:
        raise AuthenticationError("The URL has no authorization code") from None


class GoogleAuth:
    """Google OAuth2 authentication handler.

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

    # Set per instance by __init__; from_service_account never needs one
    _client_config: dict[str, Any] | None = None

    def __init__(
        self,
        token_store: TokenStore | None = None,
        credentials_file: str | None = None,
        scopes: list[str] | None = None,
        user_id: str = "default",
        client_config: dict[str, Any] | None = None,
    ):
        """Initialize OAuth authenticator.

        Args:
            token_store: Storage backend for tokens (default: SQLite)
            credentials_file: Path to OAuth credentials JSON
            scopes: OAuth scopes to request (default: Scopes.default(), i.e.
                Gmail, Calendar, Drive and Sheets)
            user_id: User identifier for multi-user setups
            client_config: The OAuth client as Google's JSON would hold it
                ({"installed": {...}} or {"web": {...}}), instead of a file;
                see ``from_client_config``
        """
        settings = get_settings()

        self.token_store: TokenStore | None = token_store or SQLiteTokenStore(
            settings.token_db_path
        )
        self.credentials_file = Path(credentials_file or settings.credentials_file)
        self.scopes = scopes or Scopes.default()
        self.user_id = user_id
        self._credentials: Credentials | None = None
        # An explicit credentials_file wins over GSUITE_CLIENT_ID/SECRET
        env_client = settings.client_id and settings.client_secret
        if client_config is None and credentials_file is None and env_client:
            client_config = _installed_config(str(settings.client_id), str(settings.client_secret))
        self._client_config = client_config

    @classmethod
    def from_client_config(
        cls,
        client_id: str,
        client_secret: str,
        scopes: list[str] | None = None,
        token_store: TokenStore | None = None,
        user_id: str = "default",
    ) -> "GoogleAuth":
        """Authenticator for an OAuth client given by ID and secret (no JSON file).

        For servers configured from env or a settings page. The same
        ``GSUITE_CLIENT_ID`` / ``GSUITE_CLIENT_SECRET`` are read by the plain
        constructor too. Pair it with ``start_authorization`` when there is no
        browser on the machine.
        """
        return cls(
            token_store=token_store,
            scopes=scopes,
            user_id=user_id,
            client_config=_installed_config(client_id, client_secret),
        )

    @classmethod
    def from_service_account(
        cls,
        service_account_file: str,
        scopes: list[str] | None = None,
        subject: str | None = None,
    ) -> "GoogleAuth":
        """Create authenticator from service account.

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
        """Refresh expired credentials.

        Returns:
            True if refresh succeeded

        Raises:
            TokenRefreshError: If refresh fails
        """
        if not self.needs_refresh() or self._credentials is None:
            return False

        try:
            self._credentials.refresh(Request())
        except (RefreshError, TransportError) as e:
            raise TokenRefreshError(cause=e) from e
        # a token store failure is not a refresh failure: let it surface as-is
        self._save_credentials()
        return True

    def authenticate(self, force: bool = False) -> Credentials:
        """Get valid credentials, running OAuth flow if needed.

        Args:
            force: Force new authentication even if credentials exist

        Returns:
            Valid Google credentials

        Raises:
            CredentialsNotFoundError: If the browser flow is needed and the
                credentials file doesn't exist
        """
        if not force:
            if self.is_authenticated() and self._credentials is not None:
                return self._credentials

            if self.needs_refresh() and self.refresh() and self._credentials is not None:
                return self._credentials

        flow = InstalledAppFlow.from_client_config(self.client_config(), self.scopes)

        self._credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )

        self._save_credentials()
        return self._credentials

    def client_config(self) -> dict[str, Any]:
        """The OAuth client: the one given, or GSUITE_CLIENT_ID/SECRET, or the credentials file.

        Raises:
            CredentialsNotFoundError: None of them is available
        """
        if self._client_config is not None:
            return self._client_config
        if not self.credentials_file.exists():
            raise CredentialsNotFoundError(str(self.credentials_file))
        config: dict[str, Any] = json.loads(self.credentials_file.read_text(encoding="utf-8"))
        return config

    def start_authorization(self, redirect_uri: str = DEFAULT_REDIRECT_URI) -> AuthorizationRequest:
        """First half of a login on a machine without a browser (PKCE).

        Show ``request.url`` to the user; after consenting, Google redirects
        to ``redirect_uri`` with a code. Pass what they bring back (the code or
        the whole URL) to ``finish_authorization`` with this request.

        Args:
            redirect_uri: Where Google sends the user back. The default works
                with Desktop clients: the browser lands on an error page whose
                URL holds the code. A web client needs its registered URI.
        """
        flow = Flow.from_client_config(
            self.client_config(),
            self.scopes,
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=True,
        )
        url, state = flow.authorization_url(access_type="offline", prompt="consent")
        return AuthorizationRequest(
            url=url, state=state, code_verifier=str(flow.code_verifier), redirect_uri=redirect_uri
        )

    def finish_authorization(self, request: AuthorizationRequest, code_or_url: str) -> Credentials:
        """Second half: exchange the code for tokens and store them.

        Args:
            request: What ``start_authorization`` returned (possibly rebuilt
                with ``AuthorizationRequest.from_dict``)
            code_or_url: The code, or the whole redirect URL as pasted; a URL
                must carry the request's ``state``

        Raises:
            AuthenticationError: Google declined, the URL is from another
                attempt, or the code was rejected
        """
        code = _code_from(code_or_url, request.state)
        flow = Flow.from_client_config(
            self.client_config(),
            self.scopes,
            redirect_uri=request.redirect_uri,
            code_verifier=request.code_verifier,
            autogenerate_code_verifier=False,
        )
        try:
            flow.fetch_token(code=code)
        except Warning as changed:
            # oauthlib raises when Google grants other scopes than asked, e.g. it
            # adds "openid" to userinfo scopes; the token is fine and comes along
            token = getattr(changed, "token", None)
            if token is None:
                raise AuthenticationError(f"Google rejected the login: {changed}") from changed
            flow.oauth2session.token = token
        except Exception as exc:
            raise AuthenticationError(f"Google rejected the authorization code: {exc}") from exc
        self._credentials = flow.credentials
        self._save_credentials()
        return self._credentials

    def revoke(self) -> bool:
        """Revoke and delete stored credentials.

        Returns:
            True if credentials were deleted
        """
        self._credentials = None
        if self.token_store:
            return self.token_store.delete_token(self.user_id)
        return False

    def export_token(self) -> dict[str, Any] | None:
        """Export token data for external storage.

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
        """Get authenticated user's email.

        Returns:
            Email address or None
        """
        if not self.is_authenticated():
            return None

        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        try:
            service = build("oauth2", "v2", credentials=self._credentials)
            user_info = service.userinfo().get().execute()
            email = user_info.get("email")
            return str(email) if email else None
        except (HttpError, GoogleAuthError, httplib2.HttpLib2Error, OSError):
            return None


def _installed_config(client_id: str, client_secret: str) -> dict[str, Any]:
    """A Desktop ("installed") client config, as in Google's downloaded JSON."""
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
