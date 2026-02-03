"""Authentication module."""

from gsuite_core.auth.oauth import GoogleAuth
from gsuite_core.auth.scopes import Scopes

__all__ = ["GoogleAuth", "Scopes"]
