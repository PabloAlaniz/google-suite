"""Login without a browser (client config + two-step PKCE flow) and missing-scope errors."""

import json
from unittest.mock import MagicMock, PropertyMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from google_auth_oauthlib.flow import Flow

from gsuite_core import GoogleAuth, Settings
from gsuite_core.api_utils import error_for_status, reason_from_body
from gsuite_core.auth.oauth import AuthorizationRequest
from gsuite_core.exceptions import (
    AuthenticationError,
    CredentialsNotFoundError,
    InsufficientScopeError,
    PermissionDeniedError,
)
from gsuite_core.storage import TokenStore


class MemoryStore(TokenStore):
    """A TokenStore an app could back with its own table."""

    def __init__(self):
        self.tokens = {}

    def get_token(self, user_id="default"):
        return self.tokens.get(user_id)

    def save_token(self, token_data, user_id="default"):
        self.tokens[user_id] = token_data

    def delete_token(self, user_id="default"):
        return self.tokens.pop(user_id, None) is not None

    def exists(self, user_id="default"):
        return user_id in self.tokens


@pytest.fixture
def settings():
    s = Settings(credentials_file="/nonexistent/credentials.json", _env_file=None)
    with patch("gsuite_core.auth.oauth.get_settings", return_value=s):
        yield s


@pytest.fixture
def auth(settings):
    return GoogleAuth.from_client_config(
        "id-123.apps.googleusercontent.com", "secret", token_store=MemoryStore()
    )


def query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


class TestClientConfig:
    def test_from_client_config_needs_no_file(self, auth):
        config = auth.client_config()["installed"]

        assert (config["client_id"], config["client_secret"]) == (
            "id-123.apps.googleusercontent.com",
            "secret",
        )

    def test_env_client_id_and_secret(self, settings):
        settings.client_id, settings.client_secret = "env-id", "env-secret"

        auth = GoogleAuth(token_store=MemoryStore())

        assert auth.client_config()["installed"]["client_id"] == "env-id"

    def test_explicit_file_wins_over_env(self, settings, tmp_path):
        settings.client_id, settings.client_secret = "env-id", "env-secret"
        path = tmp_path / "credentials.json"
        path.write_text(json.dumps({"installed": {"client_id": "file-id"}}))

        auth = GoogleAuth(token_store=MemoryStore(), credentials_file=str(path))

        assert auth.client_config()["installed"]["client_id"] == "file-id"

    def test_no_client_at_all(self, settings):
        with pytest.raises(CredentialsNotFoundError):
            GoogleAuth(token_store=MemoryStore()).client_config()


class TestTwoStepLogin:
    def test_start_builds_a_pkce_consent_url(self, auth):
        request = auth.start_authorization()

        params = query(request.url)
        assert params["client_id"] == "id-123.apps.googleusercontent.com"
        assert params["redirect_uri"] == "http://localhost"
        assert (params["access_type"], params["prompt"]) == ("offline", "consent")
        assert params["code_challenge_method"] == "S256"
        assert params["code_challenge"]
        assert params["state"] == request.state
        assert len(request.code_verifier) >= 43  # RFC 7636 minimum

    def test_request_survives_a_round_trip(self, auth):
        request = auth.start_authorization("https://pi.local/oauth/callback")

        assert AuthorizationRequest.from_dict(json.loads(json.dumps(request.to_dict()))) == request

    @pytest.mark.parametrize(
        "pasted", ["CODE", "  CODE\n", "http://localhost/?state={state}&code=CODE"]
    )
    def test_finish_with_the_code_or_the_url(self, auth, pasted):
        request = auth.start_authorization()
        credentials = MagicMock(
            token="t", refresh_token="r", token_uri="u", client_id="c", client_secret="s", scopes=[]
        )

        with (
            patch.object(Flow, "fetch_token", autospec=True) as fetch,
            patch.object(Flow, "credentials", new_callable=PropertyMock, return_value=credentials),
        ):
            result = auth.finish_authorization(request, pasted.format(state=request.state))

        assert result is credentials
        (flow,) = fetch.call_args.args
        assert fetch.call_args.kwargs == {"code": "CODE"}
        # the exchange proves possession of the verifier the URL was built with
        assert flow.code_verifier == request.code_verifier
        assert flow.redirect_uri == request.redirect_uri
        assert auth.token_store.get_token()["refresh_token"] == "r"

    def test_url_from_another_attempt_is_refused(self, auth):
        request = auth.start_authorization()

        with pytest.raises(AuthenticationError, match="another login"):
            auth.finish_authorization(request, "http://localhost/?state=other&code=CODE")

    def test_declined_consent(self, auth):
        request = auth.start_authorization()
        url = f"http://localhost/?state={request.state}&error=access_denied"

        with pytest.raises(AuthenticationError, match="access_denied"):
            auth.finish_authorization(request, url)

    def test_rejected_code(self, auth):
        request = auth.start_authorization()

        with (
            patch.object(Flow, "fetch_token", side_effect=ValueError("invalid_grant")),
            pytest.raises(AuthenticationError, match="invalid_grant"),
        ):
            auth.finish_authorization(request, "CODE")

        assert auth.token_store.get_token() is None


class TestMissingScope:
    @pytest.mark.parametrize(
        "body",
        [
            {"error": {"code": 403, "errors": [{"reason": "insufficientPermissions"}]}},
            # newer format: no "errors", an ErrorInfo in "details" (People API)
            {
                "error": {
                    "code": 403,
                    "status": "PERMISSION_DENIED",
                    "details": [
                        {"@type": "type.googleapis.com/google.rpc.ErrorInfo"},
                        {"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"},
                    ],
                }
            },
        ],
    )
    def test_is_its_own_permission_error(self, body):
        reason = reason_from_body(json.dumps(body))

        error = error_for_status(403, reason, "nope", "contacts")

        assert isinstance(error, InsufficientScopeError)
        assert isinstance(error, PermissionDeniedError)  # existing handlers still catch it
        assert error.status_code == 403
        assert "contacts" in error.message

    def test_other_403s_stay_permission_denied(self):
        error = error_for_status(403, "forbidden", "nope", "drive")

        assert type(error) is PermissionDeniedError
