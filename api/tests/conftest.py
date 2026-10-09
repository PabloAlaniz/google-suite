"""Fixtures for REST API tests: an app with its own settings and mocked Google clients."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from gsuite_api import dependencies
from gsuite_api.main import create_app
from gsuite_core import Settings

API_KEY = "test-api-key"


@pytest.fixture
def settings():
    return Settings(api_key=API_KEY, _env_file=None)


@pytest.fixture
def services():
    """Mocked Google clients, one per service, injected into the routes."""
    return {
        "gmail": MagicMock(name="gmail"),
        "calendar": MagicMock(name="calendar"),
        "drive": MagicMock(name="drive"),
        "sheets": MagicMock(name="sheets"),
        "tasks": MagicMock(name="tasks"),
        "contacts": MagicMock(name="contacts"),
    }


@pytest.fixture
def google_auth():
    auth = MagicMock(name="google_auth")
    auth.is_authenticated.return_value = True
    auth.needs_refresh.return_value = False
    return auth


@pytest.fixture
def make_client(services, google_auth):
    """Build a TestClient for an app created with the given settings."""

    def _make(settings: Settings, raise_server_exceptions: bool = True) -> TestClient:
        app = create_app(settings)
        # Never touch the real token store (it would create tokens.db).
        app.dependency_overrides[dependencies.get_auth] = lambda: google_auth
        app.dependency_overrides[dependencies.get_gmail] = lambda: services["gmail"]
        app.dependency_overrides[dependencies.get_calendar] = lambda: services["calendar"]
        app.dependency_overrides[dependencies.get_drive] = lambda: services["drive"]
        app.dependency_overrides[dependencies.get_sheets] = lambda: services["sheets"]
        app.dependency_overrides[dependencies.get_tasks] = lambda: services["tasks"]
        app.dependency_overrides[dependencies.get_contacts] = lambda: services["contacts"]
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    return _make


@pytest.fixture
def client(make_client, settings):
    """Client with a valid X-API-Key on every request."""
    test_client = make_client(settings)
    test_client.headers["X-API-Key"] = API_KEY
    return test_client


@pytest.fixture
def anonymous(make_client, settings):
    """Client that sends no API key."""
    return make_client(settings)
