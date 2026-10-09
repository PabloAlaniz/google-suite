"""Opt-in tests against a real Google account.

Skipped unless GSUITE_INTEGRATION=1. Credentials come from, in order:

- GSUITE_INTEGRATION_TOKEN: the JSON printed by `gsuite auth export` (CI);
- the local token store (`gsuite auth login`).

Use a throwaway account: every test creates its own resources (named
``gsuite-it-<random>``) and deletes them when it ends. Tasks and Contacts
tests are skipped when the token lacks their scopes; log in with
`gsuite auth login --force --scopes all` to run everything.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from typing import Any

import pytest

from gsuite_core import GoogleAuth, Scopes, TokenStore

ENABLED = os.environ.get("GSUITE_INTEGRATION") == "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if ENABLED:
        return
    skip = pytest.mark.skip(reason="integration tests: set GSUITE_INTEGRATION=1")
    for item in items:
        if "tests/integration" in str(item.path):
            item.add_marker(skip)


class MemoryTokenStore(TokenStore):
    """Holds the exported token; refreshed tokens are kept for the session only."""

    def __init__(self, token: dict[str, Any]) -> None:
        self._token: dict[str, Any] | None = token

    def get_token(self, user_id: str = "default") -> dict[str, Any] | None:
        return self._token

    def save_token(self, token_data: dict[str, Any], user_id: str = "default") -> None:
        self._token = token_data

    def delete_token(self, user_id: str = "default") -> bool:
        self._token = None
        return True

    def exists(self, user_id: str = "default") -> bool:
        return self._token is not None


@pytest.fixture(scope="session")
def auth() -> GoogleAuth:
    exported = os.environ.get("GSUITE_INTEGRATION_TOKEN")
    if exported:
        google_auth = GoogleAuth(token_store=MemoryTokenStore(json.loads(exported)))
    else:
        google_auth = GoogleAuth()

    if not google_auth.is_authenticated():
        if not google_auth.needs_refresh():
            pytest.skip("no Google token: run `gsuite auth login` or set GSUITE_INTEGRATION_TOKEN")
        google_auth.refresh()
    return google_auth


@pytest.fixture(scope="session")
def granted(auth: GoogleAuth) -> set[str]:
    return set(auth.credentials.scopes or [])


def _require(granted: set[str], scopes: list[str], what: str) -> None:
    if not set(scopes) <= granted:
        pytest.skip(f"token lacks the {what} scope: gsuite auth login --force --scopes all")


@pytest.fixture
def need_scopes(granted: set[str]) -> Callable[[list[str], str], None]:
    """``need_scopes(Scopes.tasks(), "Tasks")`` skips the test unless they were granted."""
    return lambda scopes, what: _require(granted, scopes, what)


@pytest.fixture
def name() -> str:
    """A unique name for the resources a test creates."""
    return f"gsuite-it-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _default_scopes(granted: set[str]) -> None:
    """Every test needs at least the default login (Gmail, Calendar, Drive, Sheets)."""
    _require(granted, Scopes.default(), "default")
