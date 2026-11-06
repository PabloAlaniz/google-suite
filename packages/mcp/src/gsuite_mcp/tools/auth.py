"""Login status."""

from __future__ import annotations

from typing import Any

from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    ToolDecorator,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the auth tools on the server."""

    @tool(READ)
    def auth_status() -> dict[str, Any]:
        """Whether the server has a valid Google login, and for which account and scopes."""
        auth = svc.auth()
        credentials = auth.credentials
        return {
            "authenticated": True,
            "email": auth.get_user_email(),
            "scopes": sorted(credentials.scopes or []) if credentials else [],
        }
