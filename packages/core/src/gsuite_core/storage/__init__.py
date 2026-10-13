"""Token storage implementations."""

from gsuite_core.storage.base import TokenStore
from gsuite_core.storage.sqlite import SQLiteTokenStore

__all__ = ["SQLiteTokenStore", "TokenStore"]

try:
    # Redundant alias marks an explicit re-export of the optional backend.
    from gsuite_core.storage.secretmanager import (
        SecretManagerTokenStore as SecretManagerTokenStore,
    )

    __all__.append("SecretManagerTokenStore")
except ImportError:
    pass
