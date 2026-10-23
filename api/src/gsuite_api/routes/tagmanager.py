"""Tag Manager routes (read-only). Parents are API paths passed as `parent`."""

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from gsuite_api.dependencies import TagManagerDep

router = APIRouter()

ACCOUNT = Query(pattern=r"^accounts/\d+$", description='"accounts/123"')
CONTAINER = Query(pattern=r"^accounts/\d+/containers/\d+$", description='"accounts/1/containers/2"')
WORKSPACE = Query(
    pattern=r"^accounts/\d+/containers/\d+/workspaces/\d+$",
    description='"accounts/1/containers/2/workspaces/3"',
)


class _Entity(BaseModel):
    """Read from the SDK dataclass attributes (its ``raw`` is left out)."""

    model_config = ConfigDict(from_attributes=True)

    path: str
    name: str
    tag_manager_url: str | None = None


class AccountResponse(_Entity):
    account_id: str


class ContainerResponse(_Entity):
    account_id: str
    container_id: str
    public_id: str
    usage_context: list[str]
    domain_names: list[str]
    notes: str | None


class WorkspaceResponse(_Entity):
    workspace_id: str
    description: str | None


class TagResponse(_Entity):
    tag_id: str
    type: str
    firing_trigger_ids: list[str]
    blocking_trigger_ids: list[str]
    paused: bool
    parameters: list[dict[str, Any]]


class TriggerResponse(_Entity):
    trigger_id: str
    type: str


class VariableResponse(_Entity):
    variable_id: str
    type: str
    parameters: list[dict[str, Any]]


class VersionHeaderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    container_version_id: str
    name: str
    num_tags: int
    num_triggers: int
    num_variables: int
    deleted: bool


def _list(key: str, model: type[BaseModel], items: Sequence[object]) -> dict[str, Any]:
    return {key: [model.model_validate(i) for i in items], "count": len(items)}


@router.get("/accounts")
def list_accounts(gtm: TagManagerDep) -> dict[str, Any]:
    return _list("accounts", AccountResponse, gtm.list_accounts())


@router.get("/containers")
def list_containers(gtm: TagManagerDep, parent: str = ACCOUNT) -> dict[str, Any]:
    return _list("containers", ContainerResponse, gtm.list_containers(parent))


@router.get("/workspaces")
def list_workspaces(gtm: TagManagerDep, parent: str = CONTAINER) -> dict[str, Any]:
    return _list("workspaces", WorkspaceResponse, gtm.list_workspaces(parent))


@router.get("/versions")
def list_versions(gtm: TagManagerDep, parent: str = CONTAINER) -> dict[str, Any]:
    return _list("versions", VersionHeaderResponse, gtm.list_versions(parent))


@router.get("/tags")
def list_tags(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("tags", TagResponse, gtm.list_tags(parent))


@router.get("/triggers")
def list_triggers(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("triggers", TriggerResponse, gtm.list_triggers(parent))


@router.get("/variables")
def list_variables(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("variables", VariableResponse, gtm.list_variables(parent))
