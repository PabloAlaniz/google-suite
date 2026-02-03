"""Token storage implementations."""

from gsuite_core.storage.base import TokenStore
from gsuite_core.storage.sqlite import SQLiteTokenStore

__all__ = ["TokenStore", "SQLiteTokenStore"]

try:
    from gsuite_core.storage.secretmanager import SecretManagerTokenStore

    __all__.append("SecretManagerTokenStore")
except ImportError:
    pass
