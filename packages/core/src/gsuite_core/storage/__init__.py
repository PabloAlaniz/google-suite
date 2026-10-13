"""Token storage implementations."""

from gsuite_core.storage.base import TokenStore
from gsuite_core.storage.sqlite import SQLiteTokenStore

__all__ = ["SQLiteTokenStore", "TokenStore"]

try:
    from gsuite_core.storage.secretmanager import SecretManagerTokenStore

    __all__.append("SecretManagerTokenStore")
except ImportError:
    pass
