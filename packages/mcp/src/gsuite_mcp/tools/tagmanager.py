"""Tag Manager tools (read-only)."""

from __future__ import annotations

from typing import Any

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    ToolDecorator,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the tagmanager tools on the server."""

    @tool(READ)
    def tagmanager_list_accounts() -> dict[str, Any]:
        """Tag Manager accounts (path like "accounts/123")."""
        return results(to_json(svc.tagmanager.list_accounts()))

    @tool(READ)
    def tagmanager_list_containers(account_path: str) -> dict[str, Any]:
        """Containers of an account ("accounts/123"), with their public GTM-XXXX id."""
        return results(to_json(svc.tagmanager.list_containers(account_path)))

    @tool(READ)
    def tagmanager_list_workspaces(container_path: str) -> dict[str, Any]:
        """Workspaces of a container ("accounts/123/containers/456")."""
        return results(to_json(svc.tagmanager.list_workspaces(container_path)))

    @tool(READ)
    def tagmanager_list_tags(workspace_path: str) -> dict[str, Any]:
        """Tags of a workspace ("accounts/1/containers/2/workspaces/3")."""
        return results(to_json(svc.tagmanager.list_tags(workspace_path)))

    @tool(READ)
    def tagmanager_list_triggers(workspace_path: str) -> dict[str, Any]:
        """Triggers of a workspace ("accounts/1/containers/2/workspaces/3")."""
        return results(to_json(svc.tagmanager.list_triggers(workspace_path)))

    @tool(READ)
    def tagmanager_list_variables(workspace_path: str) -> dict[str, Any]:
        """Variables of a workspace ("accounts/1/containers/2/workspaces/3")."""
        return results(to_json(svc.tagmanager.list_variables(workspace_path)))

    @tool(READ)
    def tagmanager_list_versions(container_path: str) -> dict[str, Any]:
        """Version headers of a container ("accounts/123/containers/456")."""
        return results(to_json(svc.tagmanager.list_versions(container_path)))
