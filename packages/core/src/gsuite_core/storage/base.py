"""Token store interface."""

from abc import ABC, abstractmethod
from typing import Any


class TokenStore(ABC):
    """
    Abstract interface for OAuth token storage.

    Implementations can store tokens in:
    - SQLite (local development)
    - Secret Manager (Cloud Run)
    - Redis, files, etc.
    """

    @abstractmethod
    def get_token(self, user_id: str = "default") -> dict[str, Any] | None:
        """
        Retrieve stored token data.

        Args:
            user_id: User identifier for multi-user setups

        Returns:
            Token data dict or None if not found
        """
        pass

    @abstractmethod
    def save_token(self, token_data: dict[str, Any], user_id: str = "default") -> None:
        """
        Store token data.

        Args:
            token_data: Token data to store
            user_id: User identifier
        """
        pass

    @abstractmethod
    def delete_token(self, user_id: str = "default") -> bool:
        """
        Delete stored token.

        Args:
            user_id: User identifier

        Returns:
            True if token was deleted
        """
        pass

    @abstractmethod
    def exists(self, user_id: str = "default") -> bool:
        """
        Check if token exists.

        Args:
            user_id: User identifier

        Returns:
            True if token exists
        """
        pass
