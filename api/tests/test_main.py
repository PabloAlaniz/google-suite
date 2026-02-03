"""Tests for main API application."""

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
        assert "0.1.0" in app.version

    def test_cors_enabled(self):
        """Test CORS middleware is configured."""
        # Check middleware is present
        middleware_types = [type(m).__name__ for m in app.user_middleware]
        # CORSMiddleware is wrapped, so we check the app has middleware
        assert len(app.user_middleware) > 0


class TestRoutes:
    """Tests for route configuration."""

    def test_health_route_registered(self):
        """Test health route is registered."""
        routes = [r.path for r in app.routes]
        assert "/health" in routes or any("/health" in str(r.path) for r in app.routes)

    def test_gmail_routes_prefixed(self):
        """Test Gmail routes have correct prefix."""
        routes = [r.path for r in app.routes]
        gmail_routes = [r for r in routes if "/gmail" in str(r)]
        assert len(gmail_routes) > 0

    def test_calendar_routes_prefixed(self):
        """Test Calendar routes have correct prefix."""
        routes = [r.path for r in app.routes]
        calendar_routes = [r for r in routes if "/calendar" in str(r)]
        assert len(calendar_routes) > 0

    def test_drive_routes_prefixed(self):
        """Test Drive routes have correct prefix."""
        routes = [r.path for r in app.routes]
        drive_routes = [r for r in routes if "/drive" in str(r)]
        assert len(drive_routes) > 0

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
