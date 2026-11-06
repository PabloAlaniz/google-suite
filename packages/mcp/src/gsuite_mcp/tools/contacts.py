"""Contacts tools: search and get contacts."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    ToolDecorator,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the contacts tools on the server."""

    @tool(READ)
    def contacts_search(query: str, max_results: int = 10) -> dict[str, Any]:
        """Contacts whose name, email, phone or company starts with `query`
        (max 30). Needs the Contacts scope.
        """
        return results(to_json(svc.contacts.search(query, max_results=max_results)))

    @tool(READ)
    def contacts_get(contact_id: str) -> dict[str, Any]:
        """One contact by ID ("c123" or "people/c123")."""
        contact = svc.contacts.get(contact_id)
        if contact is None:
            raise ToolError(f"No contact {contact_id}")
        return to_json(contact)  # type: ignore[no-any-return]
