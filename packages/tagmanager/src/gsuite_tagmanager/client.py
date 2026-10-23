"""Tag Manager client (read-only): accounts, containers, workspaces, tags, triggers,
variables and versions."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute, paginate
from gsuite_tagmanager.models import (
    Account,
    Container,
    ContainerVersion,
    Tag,
    Trigger,
    Variable,
    VersionHeader,
    Workspace,
)
from gsuite_tagmanager.parser import (
    parse_account,
    parse_container,
    parse_container_version,
    parse_tag,
    parse_trigger,
    parse_variable,
    parse_version_header,
    parse_workspace,
)


def _paged(list_method: Any, key: str, kind: str, parent: str | None = None) -> list[Any]:
    """GTM list calls page with pageToken but take no page size."""
    params: dict[str, Any] = {"parent": parent} if parent else {}
    return list(
        paginate(
            list_method,
            key,
            "tagmanager",
            page_size_param=None,
            resource_type=kind,
            resource_id=parent or "-",
            **params,
        )
    )


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

    def list_accounts(self) -> list[Account]:
        """Accounts the user can see."""
        return [parse_account(a) for a in _paged(self._accounts.list, "account", "accounts")]

    def list_containers(self, account_path: str) -> list[Container]:
        """Containers of an account, e.g. ``accounts/1``."""
        res = self._accounts.containers()
        items = _paged(res.list, "container", "containers", account_path)
        return [parse_container(c) for c in items]

    def list_workspaces(self, container_path: str) -> list[Workspace]:
        """Workspaces of a container, e.g. ``accounts/1/containers/2``."""
        res = self._accounts.containers().workspaces()
        items = _paged(res.list, "workspace", "workspaces", container_path)
        return [parse_workspace(w) for w in items]

    def _workspace_list(self, kind: str, key: str, workspace_path: str) -> list[Any]:
        res = getattr(self._accounts.containers().workspaces(), kind)()
        return _paged(res.list, key, kind, workspace_path)

    def list_tags(self, workspace_path: str) -> list[Tag]:
        """Tags of a workspace, e.g. ``accounts/1/containers/2/workspaces/3``."""
        return [parse_tag(t) for t in self._workspace_list("tags", "tag", workspace_path)]

    def list_triggers(self, workspace_path: str) -> list[Trigger]:
        """Triggers of a workspace."""
        items = self._workspace_list("triggers", "trigger", workspace_path)
        return [parse_trigger(t) for t in items]

    def list_variables(self, workspace_path: str) -> list[Variable]:
        """User-defined variables of a workspace."""
        items = self._workspace_list("variables", "variable", workspace_path)
        return [parse_variable(v) for v in items]

    def list_versions(self, container_path: str) -> list[VersionHeader]:
        """Version headers (id, name, counts) of a container, newest last."""
        res = self._accounts.containers().version_headers()
        items = _paged(res.list, "containerVersionHeader", "versions", container_path)
        return [parse_version_header(v) for v in items]

    def get_live_version(self, container_path: str) -> ContainerVersion:
        """The published container version, with its tags/triggers/variables."""
        data = execute(
            self._accounts.containers().versions().live(parent=container_path),
            "tagmanager",
            "version",
            container_path,
        )
        return parse_container_version(dict(data))
