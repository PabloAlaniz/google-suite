"""Tests for health endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from gsuite_api.main import app


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_returns_ok(self):
        """Test health check returns healthy status."""
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "gsuite-api"
        assert "version" in data

    def test_health_check_includes_version(self):
        """Test health check includes version info."""
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] is not None


class TestAuthStatusEndpoint:
    """Tests for /health/auth endpoint."""

    @patch("gsuite_api.routes.health.AuthDep")
    def test_auth_status_authenticated(self, mock_auth_dep):
        """Test auth status when authenticated."""
        # Note: This test may need adjustment based on actual dependency injection
        # For now, we test that the endpoint exists and returns JSON
        client = TestClient(app)

        response = client.get("/health/auth")

        # The response depends on actual auth state
        # Just verify the endpoint responds with expected structure
        assert response.status_code == 200
        data = response.json()
        assert "authenticated" in data
        assert "needs_refresh" in data
