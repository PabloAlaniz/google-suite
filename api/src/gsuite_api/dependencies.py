"""FastAPI dependencies."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from gsuite_calendar import Calendar
from gsuite_core import GoogleAuth, Settings, SQLiteTokenStore, get_settings
from gsuite_gmail import Gmail

# API Key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str | None:
    """Validate API key if configured."""
    if not settings.api_key:
        return None

    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    return api_key


@lru_cache
def get_auth() -> GoogleAuth:
    """Get shared GoogleAuth instance."""
    settings = get_settings()

    if settings.token_storage == "secretmanager":
        settings.validate_for_secretmanager()
        from gsuite_core import SecretManagerTokenStore

        token_store = SecretManagerTokenStore(
            project_id=settings.gcp_project_id,
            secret_name=settings.token_secret_name,
        )
    else:
        token_store = SQLiteTokenStore(settings.token_db_path)

    return GoogleAuth(token_store=token_store)


def get_gmail(
    auth: Annotated[GoogleAuth, Depends(get_auth)],
    _api_key: Annotated[str | None, Depends(get_api_key)],
) -> Gmail:
    """Get authenticated Gmail client."""
    if not auth.is_authenticated():
        if auth.needs_refresh():
            if not auth.refresh():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired. Re-authenticate required.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Run OAuth flow first.",
            )

    return Gmail(auth)


def get_calendar(
    auth: Annotated[GoogleAuth, Depends(get_auth)],
    _api_key: Annotated[str | None, Depends(get_api_key)],
) -> Calendar:
    """Get authenticated Calendar client."""
    if not auth.is_authenticated():
        if auth.needs_refresh():
            if not auth.refresh():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired. Re-authenticate required.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Run OAuth flow first.",
            )

    return Calendar(auth)


# Type aliases
GmailDep = Annotated[Gmail, Depends(get_gmail)]
CalendarDep = Annotated[Calendar, Depends(get_calendar)]
AuthDep = Annotated[GoogleAuth, Depends(get_auth)]
ApiKeyDep = Annotated[str | None, Depends(get_api_key)]
