"""Secret Manager token storage implementation."""

import json
import logging
from typing import Any

from google.api_core import exceptions
from google.cloud import secretmanager

from gsuite_core.storage.base import TokenStore

logger = logging.getLogger(__name__)


class SecretManagerTokenStore(TokenStore):
    """
    Google Secret Manager token storage for Cloud Run.

    Stores OAuth tokens as secrets in Google Cloud Secret Manager.
    Required for stateless deployments.
    """

    def __init__(
        self,
        project_id: str,
        secret_name: str = "gsuite-token",
        auto_create: bool = False,
    ):
        """
        Initialize Secret Manager token store.

        Args:
            project_id: GCP project ID
            secret_name: Name for the secret
            auto_create: Auto-create secret if it doesn't exist
        """
        self.project_id = project_id
        self.secret_name = secret_name
        self.auto_create = auto_create
        self.client = secretmanager.SecretManagerServiceClient()

        self._secret_path = f"projects/{project_id}/secrets/{secret_name}"

    def _get_latest_version_path(self) -> str:
        """Get path to latest secret version."""
        return f"{self._secret_path}/versions/latest"

    def _ensure_secret_exists(self) -> None:
        """Create secret if it doesn't exist and auto_create is enabled."""
        if not self.auto_create:
            return

        try:
            self.client.get_secret(request={"name": self._secret_path})
        except exceptions.NotFound:
            logger.info(f"Creating secret: {self.secret_name}")
            self.client.create_secret(
                request={
                    "parent": f"projects/{self.project_id}",
                    "secret_id": self.secret_name,
                    "secret": {"replication": {"automatic": {}}},
                }
            )

    def get_token(self, user_id: str = "default") -> dict[str, Any] | None:
        """Retrieve stored token data from Secret Manager."""
        try:
            response = self.client.access_secret_version(
                request={"name": self._get_latest_version_path()}
            )
            data = json.loads(response.payload.data.decode("utf-8"))

            if user_id in data:
                return data[user_id]
            elif user_id == "default" and "token" in data:
                return data

            return None

        except exceptions.NotFound:
            return None
        except Exception as e:
            logger.error(f"Error accessing secret: {e}")
            return None

    def save_token(self, token_data: dict[str, Any], user_id: str = "default") -> None:
        """Store token data in Secret Manager."""
        self._ensure_secret_exists()

        existing = {}
        try:
            response = self.client.access_secret_version(
                request={"name": self._get_latest_version_path()}
            )
            existing = json.loads(response.payload.data.decode("utf-8"))
        except exceptions.NotFound:
            pass

        if user_id == "default" and not existing:
            payload = token_data
        else:
            existing[user_id] = token_data
            payload = existing

        self.client.add_secret_version(
            request={
                "parent": self._secret_path,
                "payload": {"data": json.dumps(payload).encode("utf-8")},
            }
        )
        logger.info(f"Token saved to Secret Manager: {self.secret_name}")

    def delete_token(self, user_id: str = "default") -> bool:
        """Delete token from Secret Manager."""
        try:
            response = self.client.access_secret_version(
                request={"name": self._get_latest_version_path()}
            )
            data = json.loads(response.payload.data.decode("utf-8"))

            if user_id in data:
                del data[user_id]
                self.client.add_secret_version(
                    request={
                        "parent": self._secret_path,
                        "payload": {"data": json.dumps(data).encode("utf-8")},
                    }
                )
                return True
            elif user_id == "default":
                self.client.delete_secret(request={"name": self._secret_path})
                return True

            return False

        except exceptions.NotFound:
            return False

    def exists(self, user_id: str = "default") -> bool:
        """Check if token exists in Secret Manager."""
        return self.get_token(user_id) is not None
