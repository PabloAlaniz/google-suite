"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Prefix: GSUITE_
    Example: GSUITE_API_KEY=secret
    """

    # API settings
    api_key: str | None = Field(default=None, description="API key for REST endpoints")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    version: str = Field(default="dev", description="API version")

    # Google OAuth
    credentials_file: str = Field(
        default="credentials.json", description="Path to Google OAuth credentials file"
    )

    # Token storage backend
    token_storage: Literal["sqlite", "secretmanager"] = Field(
        default="sqlite", description="Token storage backend"
    )

    # SQLite storage
    token_db_path: str = Field(default="tokens.db", description="Path to SQLite token database")

    # Secret Manager (for Cloud Run)
    gcp_project_id: str | None = Field(default=None, description="GCP project ID")
    token_secret_name: str = Field(
        default="gsuite-token", description="Secret name in Secret Manager"
    )
    token_secret_auto_create: bool = Field(
        default=False, description="Auto-create secret if it doesn't exist"
    )

    # API behavior
    default_timezone: str = Field(default="UTC", description="Default timezone for calendar events")
    request_timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts for failed requests")
    retry_delay: float = Field(
        default=1.0, description="Base delay between retries in seconds (exponential backoff)"
    )
    retry_on_rate_limit: bool = Field(
        default=True, description="Whether to automatically retry on rate limit errors"
    )

    model_config = {
        "env_prefix": "GSUITE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def validate_for_secretmanager(self) -> None:
        """Validate settings when using Secret Manager."""
        if self.token_storage == "secretmanager" and not self.gcp_project_id:
            raise ValueError("GSUITE_GCP_PROJECT_ID is required when using secretmanager storage")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
