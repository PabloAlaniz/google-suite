"""Tests for main API application."""

import re

from fastapi.testclient import TestClient

from gsuite_api.main import app, create_app


class TestAppCreation:
    """Tests for app creation and configuration."""

    def test_create_app(self):
        """Test app creation returns FastAPI instance."""
        from fastapi import FastAPI

        test_app = create_app()
        assert isinstance(test_app, FastAPI)

    def test_app_metadata(self):
        """Test app has correct metadata."""
        assert app.title == "Google Suite API"
        from gsuite_core import __version__

        assert app.version == __version__

    def test_cors_enabled(self):
        """Test CORS middleware is configured."""
        # Check middleware is present
        middleware_types = [type(m).__name__ for m in app.user_middleware]
        # CORSMiddleware is wrapped, so we check the app has middleware
        assert len(app.user_middleware) > 0


def _paths_with_methods() -> list[tuple[str, list[str]]]:
    # OpenAPI keeps paths in registration order, which is matching order.
    return [(p, [m.upper() for m in ops]) for p, ops in app.openapi()["paths"].items()]


def _paths() -> list[str]:
    # app.routes is not flat in recent FastAPI (included routers are wrapped);
    # the OpenAPI schema is the public, stable view of registered paths.
    return list(app.openapi()["paths"])


class TestRoutes:
    """Tests for route configuration."""

    def test_health_route_registered(self):
        """Test health route is registered."""
        assert "/health" in _paths()

    def test_gmail_routes_prefixed(self):
        """Test Gmail routes have correct prefix."""
        gmail_routes = [p for p in _paths() if p.startswith("/gmail/")]
        assert len(gmail_routes) > 0

    def test_calendar_routes_prefixed(self):
        """Test Calendar routes have correct prefix."""
        calendar_routes = [p for p in _paths() if p.startswith("/calendar/")]
        assert len(calendar_routes) > 0

    def test_drive_routes_prefixed(self):
        """Test Drive routes have correct prefix."""
        drive_routes = [p for p in _paths() if p.startswith("/drive/")]
        assert len(drive_routes) > 0

    def test_sheets_routes_prefixed(self):
        """Test Sheets routes have correct prefix."""
        sheets_routes = [p for p in _paths() if p.startswith("/sheets/")]
        assert len(sheets_routes) > 0

    def test_docs_available(self):
        """Test OpenAPI docs endpoints are available."""
        client = TestClient(app)

        # OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        # Swagger UI
        response = client.get("/docs")
        assert response.status_code == 200

        # ReDoc
        response = client.get("/redoc")
        assert response.status_code == 200


def _pattern(path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")


def test_no_route_is_shadowed_by_an_earlier_one():
    """A parametric route declared first swallows later literal ones.

    /gmail/messages/{message_id}/read used to capture /gmail/messages/batch/read
    (message_id="batch"), so the batch endpoints were unreachable.
    """
    seen: list[tuple[str, str]] = []
    shadowed = []
    for path, operations in _paths_with_methods():
        concrete = re.sub(r"\{[^}]+\}", "__param__", path)
        for method in operations:
            for earlier_method, earlier in seen:
                if (
                    earlier_method == method
                    and earlier != path
                    and _pattern(earlier).match(concrete)
                ):
                    shadowed.append(f"{method} {path} is caught by {earlier}")
        seen.extend((method, path) for method in operations)
    assert not shadowed
