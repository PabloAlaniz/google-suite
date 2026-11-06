"""Contacts tools: search and get contacts, and manage contact groups."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    DESTRUCTIVE,
    READ,
    WRITE,
    ToolDecorator,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the contacts tools on the server."""
    _register_contacts(tool, svc)
    _register_groups(tool, svc)


def _register_contacts(tool: ToolDecorator, svc: Services) -> None:
    """Search and read contacts."""

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


def _register_groups(tool: ToolDecorator, svc: Services) -> None:
    """Contact groups: list, members, create, modify, delete."""

    @tool(READ)
    def contacts_list_groups() -> dict[str, Any]:
        """Contact groups (labels) with their member counts.

        System groups such as "myContacts" are included.
        """
        return results(to_json(svc.contacts.list_groups()))

    @tool(READ)
    def contacts_group_members(group_id: str) -> dict[str, Any]:
        """The contacts in a group (ID like "a1b2" or "contactGroups/a1b2")."""
        members = svc.contacts.group_members(group_id)
        return results(to_json(svc.contacts.get_many(members)))

    @tool(WRITE)
    def contacts_create_group(name: str) -> dict[str, Any]:
        """Create a contact group (label)."""
        return to_json(svc.contacts.create_group(name))  # type: ignore[no-any-return]

    @tool(WRITE)
    def contacts_modify_group(
        group_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> dict[str, Any]:
        """Add contacts to a group and/or remove them (contact IDs).

        Removing keeps the contact. `skipped` lists contacts Google left as they were.
        """
        if not add and not remove:
            raise ToolError("Pass contacts to add and/or remove")
        skipped = svc.contacts.modify_group(group_id, add=add, remove=remove)
        return {"skipped": skipped}

    @tool(DESTRUCTIVE)
    def contacts_delete_group(group_id: str) -> dict[str, Any]:
        """Delete a contact group; its contacts stay. Confirm with the user first."""
        if not svc.contacts.delete_group(group_id):
            raise ToolError(f"No group {group_id}")
        return {"deleted": group_id}
