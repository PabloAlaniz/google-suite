"""FastAPI dependencies."""

import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from gsuite_calendar import Calendar
from gsuite_core import GoogleAuth, Settings, SQLiteTokenStore, TokenStore, get_settings
from gsuite_core.exceptions import NotAuthenticatedError
from gsuite_drive import Drive
from gsuite_gmail import Gmail
from gsuite_sheets import Sheets

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_app_settings(request: Request) -> Settings:
    """Settings the app was created with (see create_app)."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def require_api_key(
    api_key: Annotated[str | None, Security(api_key_header)],
    settings: SettingsDep,
) -> None:
    """Reject the request unless it carries the configured API key.

    Fails closed: with no GSUITE_API_KEY set, every request is rejected
    unless GSUITE_ALLOW_NO_API_KEY explicitly opts out.
    """
    if not settings.api_key:
        if settings.allow_no_api_key:
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "API key not configured on the server. Set GSUITE_API_KEY, or "
                "GSUITE_ALLOW_NO_API_KEY=true if access is protected some other way."
            ),
        )

    if not api_key or not secrets.compare_digest(api_key.encode(), settings.api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@lru_cache
def get_auth() -> GoogleAuth:
    """Get shared GoogleAuth instance."""
    settings = get_settings()

    token_store: TokenStore
    if settings.token_storage == "secretmanager":
        settings.validate_for_secretmanager()
        assert settings.gcp_project_id  # guaranteed by validate_for_secretmanager
        from gsuite_core import SecretManagerTokenStore

        token_store = SecretManagerTokenStore(
            project_id=settings.gcp_project_id,
            secret_name=settings.token_secret_name,
        )
    else:
        token_store = SQLiteTokenStore(settings.token_db_path)

    return GoogleAuth(token_store=token_store)


AuthDep = Annotated[GoogleAuth, Depends(get_auth)]


def get_authenticated_auth(auth: AuthDep) -> GoogleAuth:
    """GoogleAuth with valid credentials, refreshing them if they expired.

    Raises NotAuthenticatedError (no token) or TokenRefreshError (refresh
    failed); the error handlers turn both into 401 responses.
    """
    if auth.is_authenticated():
        return auth
    if auth.needs_refresh():
        auth.refresh()
        return auth
    raise NotAuthenticatedError()


AuthenticatedDep = Annotated[GoogleAuth, Depends(get_authenticated_auth)]


def get_gmail(auth: AuthenticatedDep) -> Gmail:
    return Gmail(auth)


def get_calendar(auth: AuthenticatedDep) -> Calendar:
    return Calendar(auth)


def get_drive(auth: AuthenticatedDep) -> Drive:
    return Drive(auth)


def get_sheets(auth: AuthenticatedDep) -> Sheets:
    return Sheets(auth)


GmailDep = Annotated[Gmail, Depends(get_gmail)]
CalendarDep = Annotated[Calendar, Depends(get_calendar)]
DriveDep = Annotated[Drive, Depends(get_drive)]
SheetsDep = Annotated[Sheets, Depends(get_sheets)]
