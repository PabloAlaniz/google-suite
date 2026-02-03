"""Tests for configuration."""

import os

import pytest

from gsuite_core.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test default configuration values."""
        settings = Settings()

        assert settings.host == "0.0.0.0"
        assert settings.port == 8080
        assert settings.credentials_file == "credentials.json"
        assert settings.token_storage == "sqlite"
        assert settings.token_db_path == "tokens.db"

    def test_default_api_behavior(self):
        """Test default API behavior settings."""
        settings = Settings()

        assert settings.default_timezone == "UTC"
        assert settings.request_timeout == 30
        assert settings.max_retries == 3
        assert settings.retry_delay == 1.0
        assert settings.retry_on_rate_limit is True

    def test_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("GSUITE_PORT", "9000")
        monkeypatch.setenv("GSUITE_MAX_RETRIES", "5")
        monkeypatch.setenv("GSUITE_DEFAULT_TIMEZONE", "America/New_York")

        # Create new settings (don't use cached)
        settings = Settings()

        assert settings.port == 9000
        assert settings.max_retries == 5
        assert settings.default_timezone == "America/New_York"

    def test_secretmanager_validation(self):
        """Test validation for Secret Manager settings."""
        settings = Settings(token_storage="secretmanager", gcp_project_id=None)

        with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
            settings.validate_for_secretmanager()

    def test_secretmanager_valid(self):
        """Test valid Secret Manager settings."""
        settings = Settings(token_storage="secretmanager", gcp_project_id="my-project")

        # Should not raise
        settings.validate_for_secretmanager()

    def test_api_key_optional(self):
        """Test that API key is optional."""
        settings = Settings()
        assert settings.api_key is None

    def test_token_storage_literal(self):
        """Test token storage only accepts valid values."""
        settings = Settings(token_storage="sqlite")
        assert settings.token_storage == "sqlite"

        settings = Settings(token_storage="secretmanager")
        assert settings.token_storage == "secretmanager"
