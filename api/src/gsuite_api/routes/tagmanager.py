"""Tag Manager routes (read-only). Parents are API paths passed as `parent`."""

from typing import Any

from fastapi import APIRouter, Query

from gsuite_api.dependencies import TagManagerDep

router = APIRouter()

ACCOUNT = Query(pattern=r"^accounts/\d+$", description='"accounts/123"')
CONTAINER = Query(pattern=r"^accounts/\d+/containers/\d+$", description='"accounts/1/containers/2"')
WORKSPACE = Query(
    pattern=r"^accounts/\d+/containers/\d+/workspaces/\d+$",
    description='"accounts/1/containers/2/workspaces/3"',
)


def _list(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {key: items, "count": len(items)}


@router.get("/accounts")
def list_accounts(gtm: TagManagerDep) -> dict[str, Any]:
    return _list("accounts", gtm.list_accounts())


@router.get("/containers")
def list_containers(gtm: TagManagerDep, parent: str = ACCOUNT) -> dict[str, Any]:
    return _list("containers", gtm.list_containers(parent))


@router.get("/workspaces")
def list_workspaces(gtm: TagManagerDep, parent: str = CONTAINER) -> dict[str, Any]:
    return _list("workspaces", gtm.list_workspaces(parent))


@router.get("/versions")
def list_versions(gtm: TagManagerDep, parent: str = CONTAINER) -> dict[str, Any]:
    return _list("versions", gtm.list_versions(parent))


@router.get("/tags")
def list_tags(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("tags", gtm.list_tags(parent))


@router.get("/triggers")
def list_triggers(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("triggers", gtm.list_triggers(parent))


@router.get("/variables")
def list_variables(gtm: TagManagerDep, parent: str = WORKSPACE) -> dict[str, Any]:
    return _list("variables", gtm.list_variables(parent))
