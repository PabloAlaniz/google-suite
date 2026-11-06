"""FastAPI dependencies."""

import math
import secrets
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from gsuite_analytics import Analytics
from gsuite_calendar import AsyncCalendar
from gsuite_contacts import Contacts
from gsuite_core import GoogleAuth, Settings, SQLiteTokenStore, TokenStore, get_settings
from gsuite_core.exceptions import NotAuthenticatedError
from gsuite_core.rate_limit import TokenBucket
from gsuite_drive import Drive
from gsuite_gmail import Gmail
from gsuite_searchconsole import SearchConsole
from gsuite_sheets import Sheets
from gsuite_tagmanager import TagManager
from gsuite_tasks import Tasks

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


def enforce_rate_limit(request: Request) -> None:
    """Reject the request with 429 once the API's request budget is spent.

    One token bucket per app (GSUITE_API_RATE_LIMIT requests per second,
    GSUITE_API_RATE_LIMIT_BURST at once), shared by every client: the API has
    a single key, and behind a proxy the client address is the proxy's. Off
    when the rate is unset. Runs after require_api_key, so rejected requests
    don't spend the budget.
    """
    bucket: TokenBucket | None = request.app.state.rate_limiter
    if bucket is None:
        return
    wait = bucket.try_acquire()
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API rate limit exceeded",
            headers={"Retry-After": str(math.ceil(wait))},
        )


@lru_cache
def get_auth() -> GoogleAuth:
    """Get shared GoogleAuth instance."""
    settings = get_settings()

    token_store: TokenStore
    # "secretmanager" is a storage backend name, not a credential
    if settings.token_storage == "secretmanager":  # noqa: S105
        settings.validate_for_secretmanager()
        if not settings.gcp_project_id:  # validate_for_secretmanager already raised
            raise ValueError("GSUITE_GCP_PROJECT_ID is required when using secretmanager storage")
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
    raise NotAuthenticatedError


AuthenticatedDep = Annotated[GoogleAuth, Depends(get_authenticated_auth)]


def get_gmail(auth: AuthenticatedDep) -> Gmail:
    return Gmail(auth)


async def get_calendar(auth: AuthenticatedDep) -> AsyncIterator[AsyncCalendar]:
    """An AsyncCalendar for the request, closed (connection pool and all) after it."""
    async with AsyncCalendar(auth) as calendar:
        yield calendar


def get_drive(auth: AuthenticatedDep) -> Drive:
    return Drive(auth)


def get_sheets(auth: AuthenticatedDep) -> Sheets:
    return Sheets(auth)


def get_tasks(auth: AuthenticatedDep) -> Tasks:
    return Tasks(auth)


def get_contacts(auth: AuthenticatedDep) -> Contacts:
    return Contacts(auth)


def get_searchconsole(auth: AuthenticatedDep) -> SearchConsole:
    return SearchConsole(auth)


def get_analytics(auth: AuthenticatedDep) -> Analytics:
    return Analytics(auth)


def get_tagmanager(auth: AuthenticatedDep) -> TagManager:
    return TagManager(auth)


GmailDep = Annotated[Gmail, Depends(get_gmail)]
CalendarDep = Annotated[AsyncCalendar, Depends(get_calendar)]
DriveDep = Annotated[Drive, Depends(get_drive)]
SheetsDep = Annotated[Sheets, Depends(get_sheets)]
TasksDep = Annotated[Tasks, Depends(get_tasks)]
ContactsDep = Annotated[Contacts, Depends(get_contacts)]
SearchConsoleDep = Annotated[SearchConsole, Depends(get_searchconsole)]
AnalyticsDep = Annotated[Analytics, Depends(get_analytics)]
TagManagerDep = Annotated[TagManager, Depends(get_tagmanager)]
