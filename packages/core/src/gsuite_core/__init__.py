"""Google Suite Core - Shared auth, config, and utilities."""

__version__ = "0.1.0"

from gsuite_core.api_utils import api_call, api_call_optional, map_http_error
from gsuite_core.auth.oauth import GoogleAuth
from gsuite_core.auth.scopes import Scopes
from gsuite_core.config import Settings, get_settings
from gsuite_core.exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    CredentialsNotFoundError,
    GSuiteError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    TokenExpiredError,
    TokenRefreshError,
    ValidationError,
)
from gsuite_core.storage import SQLiteTokenStore, TokenStore

__all__ = [
    # Auth
    "GoogleAuth",
    "Scopes",
    # Config
    "Settings",
    "get_settings",
    # API Utils
    "api_call",
    "api_call_optional",
    "map_http_error",
    # Storage
    "TokenStore",
    "SQLiteTokenStore",
    # Exceptions
    "GSuiteError",
    "AuthenticationError",
    "CredentialsNotFoundError",
    "TokenExpiredError",
    "TokenRefreshError",
    "NotAuthenticatedError",
    "APIError",
    "RateLimitError",
    "QuotaExceededError",
    "NotFoundError",
    "PermissionDeniedError",
    "ValidationError",
    "ConfigurationError",
]

# Conditionally export SecretManagerTokenStore
try:
    from gsuite_core.storage import SecretManagerTokenStore

    __all__.append("SecretManagerTokenStore")
except ImportError:
    pass
