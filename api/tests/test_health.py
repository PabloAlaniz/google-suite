"""Tests for health endpoints."""

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
