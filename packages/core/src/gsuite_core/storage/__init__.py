"""Token storage implementations."""

from importlib import import_module
from typing import Any

from gsuite_core.config import Settings, get_settings
from gsuite_core.storage.base import TokenStore
from gsuite_core.storage.sqlite import SQLiteTokenStore

__all__ = ["SQLiteTokenStore", "TokenStore", "create_token_store"]

try:
    # Redundant alias marks an explicit re-export of the optional backend.
    from gsuite_core.storage.secretmanager import (
        SecretManagerTokenStore as SecretManagerTokenStore,
    )

    __all__.append("SecretManagerTokenStore")
except ImportError:
    pass

try:
    from gsuite_core.storage.keyring import KeyringTokenStore as KeyringTokenStore

    __all__.append("KeyringTokenStore")
except ImportError:
    pass


def _backend(module: str) -> Any:
    """An optional backend's module, imported when it is first asked for."""
    return import_module(f"gsuite_core.storage.{module}")


def create_token_store(settings: Settings | None = None) -> TokenStore:
    """The token store that ``GSUITE_TOKEN_STORAGE`` selects.

    Args:
        settings: Settings to read (default: the process settings)

    Raises:
        ValueError: Secret Manager storage without ``GSUITE_GCP_PROJECT_ID``
        ImportError: The backend's extra isn't installed
            (``gsuite-sdk[cloudrun]`` or ``gsuite-sdk[keyring]``)
    """
    settings = settings or get_settings()
    store: TokenStore
    # the comparisons below are against storage backend names, not passwords
    if settings.token_storage == "secretmanager":  # noqa: S105
        settings.validate_for_secretmanager()
        store = _backend("secretmanager").SecretManagerTokenStore(
            project_id=str(settings.gcp_project_id),
            secret_name=settings.token_secret_name,
            auto_create=settings.token_secret_auto_create,
        )
    elif settings.token_storage == "keyring":  # noqa: S105
        store = _backend("keyring").KeyringTokenStore(settings.keyring_service)
    else:
        store = SQLiteTokenStore(settings.token_db_path)
    return store
