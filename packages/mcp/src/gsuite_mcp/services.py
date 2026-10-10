"""Lazily built SDK clients sharing one GoogleAuth, and the login check."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_core import GoogleAuth, get_settings

if TYPE_CHECKING:
    from gsuite_calendar import Calendar
    from gsuite_contacts import Contacts
    from gsuite_drive import Drive
    from gsuite_gmail import Gmail
    from gsuite_sheets import Sheets
    from gsuite_tasks import Tasks


def login_hint() -> str:
    settings = get_settings()
    token_db = Path(settings.token_db_path).resolve()
    return (
        f"No valid Google login in {token_db}. Run `gsuite auth login` (add "
        "`--scopes default,tasks,contacts` for Tasks and Contacts) in the directory "
        "this server runs from, or set GSUITE_TOKEN_DB_PATH and GSUITE_CREDENTIALS_FILE "
        "to absolute paths in the server's configuration."
    )


class Services:
    """One GoogleAuth for every client; clients are created on first use."""

    def __init__(self, auth: Any = None) -> None:
        self._auth = auth

    def auth(self) -> Any:
        if self._auth is None:
            self._auth = GoogleAuth()
        auth = self._auth
        if auth.is_authenticated():
            return auth
        if auth.needs_refresh():
            auth.refresh()
            return auth
        raise ToolError(login_hint())

    @cached_property
    def gmail(self) -> Gmail:
        from gsuite_gmail import Gmail

        return Gmail(self.auth())

    @cached_property
    def calendar(self) -> Calendar:
        from gsuite_calendar import Calendar

        return Calendar(self.auth())

    @cached_property
    def drive(self) -> Drive:
        from gsuite_drive import Drive

        return Drive(self.auth())

    @cached_property
    def sheets(self) -> Sheets:
        from gsuite_sheets import Sheets

        return Sheets(self.auth())

    @cached_property
    def tasks(self) -> Tasks:
        from gsuite_tasks import Tasks

        return Tasks(self.auth())

    @cached_property
    def contacts(self) -> Contacts:
        from gsuite_contacts import Contacts

        return Contacts(self.auth())
