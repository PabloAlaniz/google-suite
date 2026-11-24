"""Selecting a stored login per request with X-GSuite-Account."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gsuite_api import dependencies
from gsuite_api.main import create_app
from gsuite_core import Settings


def _settings(**kwargs):
    return Settings(api_key="k", _env_file=None, **kwargs)


class TestGetAccount:
    def test_no_header_is_the_default_account(self):
        assert dependencies.get_account(None, _settings()) == "default"
        assert dependencies.get_account(None, _settings(account="work")) == "work"

    def test_naming_the_default_account_needs_no_allowlist(self):
        assert dependencies.get_account("work", _settings(account="work")) == "work"

    def test_listed_account_is_allowed(self):
        settings = _settings(api_accounts="work, ana@example.com")
        assert dependencies.get_account("work", settings) == "work"
        assert dependencies.get_account("ana@example.com", settings) == "ana@example.com"

    def test_wildcard_allows_any_account(self):
        assert dependencies.get_account("anything", _settings(api_accounts="*")) == "anything"

    @pytest.mark.parametrize("settings", [_settings(), _settings(api_accounts="work")])
    def test_other_accounts_are_forbidden(self, settings):
        with pytest.raises(HTTPException) as error:
            dependencies.get_account("home", settings)
        assert error.value.status_code == 403

    @pytest.mark.parametrize("name", ["", "a b", "../x", "x" * 200, "-work", "a\nb"])
    def test_malformed_name_is_rejected_before_the_allowlist(self, name):
        with pytest.raises(HTTPException) as error:
            dependencies.get_account(name, _settings(api_accounts="*"))
        assert error.value.status_code == 400


class TestThroughTheApp:
    @pytest.fixture
    def client(self):
        app = create_app(_settings(api_accounts="work"))

        @app.get("/_whoami")
        def whoami(auth: dependencies.AuthDep) -> str:
            return str(auth.user_id)

        with patch.object(
            dependencies, "auth_for", side_effect=lambda account: MagicMock(user_id=account)
        ):
            yield TestClient(app)

    def test_header_selects_the_account(self, client):
        assert client.get("/_whoami").json() == "default"
        assert client.get("/_whoami", headers={"X-GSuite-Account": "work"}).json() == "work"

    def test_account_not_enabled(self, client):
        response = client.get("/_whoami", headers={"X-GSuite-Account": "home"})
        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_openapi_documents_the_header(self, client):
        schemes = client.get("/openapi.json").json()["components"]["securitySchemes"]
        assert schemes["Account"]["name"] == "X-GSuite-Account"
