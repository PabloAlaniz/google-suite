"""Tag Manager client (read-only): accounts, containers, workspaces, tags, triggers,
variables and versions."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute


def _paged(request_factory: Any, key: str, kind: str, parent: str) -> list[dict[str, Any]]:
    """GTM list calls page with pageToken but take no page size."""
    items: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"pageToken": token} if token else {}
        data = execute(request_factory(**kwargs), "tagmanager", kind, parent)
        items.extend(data.get(key, []))
        token = data.get("nextPageToken")
        if not token:
            return items


class TagManager:
    """
    Read-only Google Tag Manager client (``tagmanager`` v2).

    Resources are addressed by their API paths: ``accounts/1``,
    ``accounts/1/containers/2``, ``accounts/1/containers/2/workspaces/3``.
    Needs ``Scopes.tagmanager()``.
    """

    def __init__(self, auth: GoogleAuth):
        self.auth = auth
        self._service: Any = None

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = build(
                "tagmanager",
                "v2",
                http=authorized_http(self.auth.credentials),
                cache_discovery=False,
            )
        return self._service

    @property
    def _accounts(self) -> Any:
        return self.service.accounts()

    def list_accounts(self) -> list[dict[str, Any]]:
        """Accounts the user can see (``path``, ``accountId``, ``name``)."""
        return _paged(self._accounts.list, "account", "accounts", "-")

    def list_containers(self, account_path: str) -> list[dict[str, Any]]:
        """Containers of an account, e.g. ``accounts/1``."""
        res = self._accounts.containers()
        return _paged(
            lambda **kw: res.list(parent=account_path, **kw),
            "container",
            "containers",
            account_path,
        )

    def list_workspaces(self, container_path: str) -> list[dict[str, Any]]:
        """Workspaces of a container, e.g. ``accounts/1/containers/2``."""
        res = self._accounts.containers().workspaces()
        return _paged(
            lambda **kw: res.list(parent=container_path, **kw),
            "workspace",
            "workspaces",
            container_path,
        )

    def _workspace_list(self, kind: str, key: str, workspace_path: str) -> list[dict[str, Any]]:
        res = getattr(self._accounts.containers().workspaces(), kind)()
        return _paged(lambda **kw: res.list(parent=workspace_path, **kw), key, kind, workspace_path)

    def list_tags(self, workspace_path: str) -> list[dict[str, Any]]:
        """Tags of a workspace, e.g. ``accounts/1/containers/2/workspaces/3``."""
        return self._workspace_list("tags", "tag", workspace_path)

    def list_triggers(self, workspace_path: str) -> list[dict[str, Any]]:
        """Triggers of a workspace."""
        return self._workspace_list("triggers", "trigger", workspace_path)

    def list_variables(self, workspace_path: str) -> list[dict[str, Any]]:
        """User-defined variables of a workspace."""
        return self._workspace_list("variables", "variable", workspace_path)

    def list_versions(self, container_path: str) -> list[dict[str, Any]]:
        """Version headers (id, name, counts) of a container, newest last."""
        res = self._accounts.containers().version_headers()
        return _paged(
            lambda **kw: res.list(parent=container_path, **kw),
            "containerVersionHeader",
            "versions",
            container_path,
        )

    def get_live_version(self, container_path: str) -> dict[str, Any]:
        """The published container version, with its tags/triggers/variables."""
        return dict(
            execute(
                self._accounts.containers().versions().live(parent=container_path),
                "tagmanager",
                "version",
                container_path,
            )
        )
