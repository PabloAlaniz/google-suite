"""API key, admin key and CORS behavior across every route."""

import re

import pytest

from gsuite_api.main import create_app
from gsuite_core import Settings

PUBLIC = {("GET", "/health")}
ADMIN = {("GET", "/health/admin/logs")}


def _all_operations():
    app = create_app(Settings(api_key="x", _env_file=None))
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method.upper(), path


OPERATIONS = sorted(set(_all_operations()))
PROTECTED = [op for op in OPERATIONS if op not in PUBLIC | ADMIN]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def test_route_inventory_is_not_empty():
    # Guards the parametrization: if OpenAPI stopped listing routes, every
    # security test below would silently pass with zero cases.
    assert len(PROTECTED) > 40


@pytest.mark.parametrize(("method", "path"), PROTECTED, ids=lambda v: str(v))
def test_protected_route_rejects_missing_key(anonymous, method, path):
    response = anonymous.request(method, _concrete(path))
    assert response.status_code == 401, response.text
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(("method", "path"), PROTECTED, ids=lambda v: str(v))
def test_protected_route_rejects_wrong_key(anonymous, method, path):
    response = anonymous.request(method, _concrete(path), headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_sheets_routes_require_key(anonymous):
    # Regression: get_sheets used to skip the API key check entirely.
    assert anonymous.get("/sheets/list").status_code == 401


def test_valid_key_is_accepted(client, services):
    services["sheets"].list_spreadsheets.return_value = []
    assert client.get("/sheets/list").status_code == 200


def test_health_is_public(anonymous):
    assert anonymous.get("/health").status_code == 200


def test_fails_closed_without_configured_key(make_client):
    anonymous = make_client(Settings(_env_file=None))
    response = anonymous.get("/gmail/labels")
    assert response.status_code == 401
    assert "GSUITE_API_KEY" in response.json()["detail"]


def test_allow_no_api_key_opt_out(make_client, services):
    services["gmail"].get_labels.return_value = []
    anonymous = make_client(Settings(allow_no_api_key=True, _env_file=None))
    assert anonymous.get("/gmail/labels").status_code == 200


class TestAdminKey:
    def test_not_configured(self, client, monkeypatch):
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
        assert client.get("/health/admin/logs").status_code == 503

    def test_wrong_header(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        response = client.get("/health/admin/logs", headers={"X-Admin-Key": "nope"})
        assert response.status_code == 401

    def test_query_param_no_longer_accepted(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        response = client.get("/health/admin/logs", params={"api_key": "admin-secret"})
        assert response.status_code == 401


class TestCors:
    def test_disabled_by_default(self, client):
        response = client.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in response.headers

    def test_configured_origin(self, make_client):
        settings = Settings(
            api_key="k", cors_origins="https://app.example, https://b.example", _env_file=None
        )
        client = make_client(settings)

        allowed = client.options(
            "/gmail/labels",
            headers={
                "Origin": "https://app.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key",
            },
        )
        assert allowed.headers["access-control-allow-origin"] == "https://app.example"
        assert "access-control-allow-credentials" not in allowed.headers

        other = client.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers

    def test_preflight_allows_every_method_the_api_uses(self, make_client):
        """PATCH routes existed while CORS only allowed GET/POST/PUT/DELETE,
        so browsers could not call them."""
        client = make_client(
            Settings(api_key="k", cors_origins="https://app.example", _env_file=None)
        )
        methods = {
            method.upper() for item in client.app.openapi()["paths"].values() for method in item
        }
        assert "PATCH" in methods
        for method in methods:
            response = client.options(
                "/health",
                headers={
                    "Origin": "https://app.example",
                    "Access-Control-Request-Method": method,
                },
            )
            assert response.status_code == 200, method
