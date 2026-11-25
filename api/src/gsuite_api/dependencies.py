"""FastAPI dependencies."""

import re
import secrets
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyHeader
from omnilimit import Limiter

from gsuite_analytics import Analytics
from gsuite_calendar import AsyncCalendar
from gsuite_contacts import Contacts
from gsuite_core import GoogleAuth, Settings, TokenStore, create_token_store, get_settings
from gsuite_core.config import ACCOUNT_PATTERN
from gsuite_core.exceptions import NotAuthenticatedError
from gsuite_drive import AsyncDrive
from gsuite_gmail import AsyncGmail
from gsuite_searchconsole import SearchConsole
from gsuite_sheets import Sheets
from gsuite_tagmanager import TagManager
from gsuite_tasks import Tasks

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
# Declared as a security scheme so /docs offers it once, for every route
account_header = APIKeyHeader(
    name="X-GSuite-Account",
    scheme_name="Account",
    description="Which stored Google login to act as (must be in GSUITE_API_ACCOUNTS)",
    auto_error=False,
)


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


def enforce_rate_limit(request: Request, response: Response) -> None:
    """Reject the request once the API's request budget is spent.

    Answers 429, or 503 if the shared store is down and configured as "closed". Off when
    GSUITE_API_RATE_LIMIT is unset. Runs after require_api_key, so rejected requests don't
    spend the budget. See gsuite_api.rate_limit.
    """
    limiter: Limiter | None = request.app.state.rate_limiter
    if limiter is None:
        return
    decision = limiter.check("api")
    if not decision.allowed:
        raise HTTPException(
            status_code=decision.status or status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "API rate limiter unavailable"
                if decision.reason == "store_error"
                else "API rate limit exceeded"
            ),
            headers=decision.headers,
        )
    # FastAPI drops these when a route returns its own Response, as downloads do.
    response.headers.update(decision.headers)


def get_account(
    account: Annotated[str | None, Security(account_header)],
    settings: SettingsDep,
) -> str:
    """The stored login the request acts as: X-GSuite-Account, or the default.

    Fails closed: a caller may only name accounts listed in
    GSUITE_API_ACCOUNTS ('*' for any). Answers 400 for a malformed name and
    403 for one that isn't allowed, without saying whether it exists.
    """
    if account is None or account == settings.account:
        return settings.account
    if not re.match(ACCOUNT_PATTERN, account):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-GSuite-Account"
        )
    allowed = settings.api_account_list
    if "*" not in allowed and account not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not enabled for the API (GSUITE_API_ACCOUNTS)",
        )
    return account


@lru_cache(maxsize=1)
def _token_store() -> TokenStore:
    return create_token_store(get_settings())


@lru_cache(maxsize=256)
def auth_for(account: str) -> GoogleAuth:
    """The shared GoogleAuth of one account (they all read the same token store)."""
    return GoogleAuth(token_store=_token_store(), user_id=account)


def get_auth(account: Annotated[str, Depends(get_account)]) -> GoogleAuth:
    """GoogleAuth for the account the request selected."""
    return auth_for(account)


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


async def get_gmail(auth: AuthenticatedDep) -> AsyncIterator[AsyncGmail]:
    """An AsyncGmail for the request, closed after it."""
    async with AsyncGmail(auth) as gmail:
        yield gmail


async def get_calendar(auth: AuthenticatedDep) -> AsyncIterator[AsyncCalendar]:
    """An AsyncCalendar for the request, closed (connection pool and all) after it."""
    async with AsyncCalendar(auth) as calendar:
        yield calendar


async def get_drive(auth: AuthenticatedDep) -> AsyncIterator[AsyncDrive]:
    """An AsyncDrive for the request, closed after it."""
    async with AsyncDrive(auth) as drive:
        yield drive


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


GmailDep = Annotated[AsyncGmail, Depends(get_gmail)]
CalendarDep = Annotated[AsyncCalendar, Depends(get_calendar)]
DriveDep = Annotated[AsyncDrive, Depends(get_drive)]
SheetsDep = Annotated[Sheets, Depends(get_sheets)]
TasksDep = Annotated[Tasks, Depends(get_tasks)]
ContactsDep = Annotated[Contacts, Depends(get_contacts)]
SearchConsoleDep = Annotated[SearchConsole, Depends(get_searchconsole)]
AnalyticsDep = Annotated[Analytics, Depends(get_analytics)]
TagManagerDep = Annotated[TagManager, Depends(get_tagmanager)]
