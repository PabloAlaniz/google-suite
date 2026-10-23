"""Convert Tag Manager API resources to entities."""

from typing import Any

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


def _int(value: Any) -> int:
    """The API sends counters as strings."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_account(data: dict[str, Any]) -> Account:
    return Account(
        path=data.get("path", ""),
        account_id=data.get("accountId", ""),
        name=data.get("name", ""),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_container(data: dict[str, Any]) -> Container:
    return Container(
        path=data.get("path", ""),
        account_id=data.get("accountId", ""),
        container_id=data.get("containerId", ""),
        name=data.get("name", ""),
        public_id=data.get("publicId", ""),
        usage_context=list(data.get("usageContext", [])),
        domain_names=list(data.get("domainName", [])),
        notes=data.get("notes"),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_workspace(data: dict[str, Any]) -> Workspace:
    return Workspace(
        path=data.get("path", ""),
        workspace_id=data.get("workspaceId", ""),
        name=data.get("name", ""),
        description=data.get("description"),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_tag(data: dict[str, Any]) -> Tag:
    return Tag(
        path=data.get("path", ""),
        tag_id=data.get("tagId", ""),
        name=data.get("name", ""),
        type=data.get("type", ""),
        firing_trigger_ids=list(data.get("firingTriggerId", [])),
        blocking_trigger_ids=list(data.get("blockingTriggerId", [])),
        paused=bool(data.get("paused", False)),
        parameters=list(data.get("parameter", [])),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_trigger(data: dict[str, Any]) -> Trigger:
    return Trigger(
        path=data.get("path", ""),
        trigger_id=data.get("triggerId", ""),
        name=data.get("name", ""),
        type=data.get("type", ""),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_variable(data: dict[str, Any]) -> Variable:
    return Variable(
        path=data.get("path", ""),
        variable_id=data.get("variableId", ""),
        name=data.get("name", ""),
        type=data.get("type", ""),
        parameters=list(data.get("parameter", [])),
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )


def parse_version_header(data: dict[str, Any]) -> VersionHeader:
    return VersionHeader(
        path=data.get("path", ""),
        container_version_id=data.get("containerVersionId", ""),
        name=data.get("name", ""),
        num_tags=_int(data.get("numTags")),
        num_triggers=_int(data.get("numTriggers")),
        num_variables=_int(data.get("numVariables")),
        deleted=bool(data.get("deleted", False)),
        raw=data,
    )


def parse_container_version(data: dict[str, Any]) -> ContainerVersion:
    return ContainerVersion(
        path=data.get("path", ""),
        container_version_id=data.get("containerVersionId", ""),
        name=data.get("name", ""),
        description=data.get("description"),
        tags=[parse_tag(t) for t in data.get("tag", [])],
        triggers=[parse_trigger(t) for t in data.get("trigger", [])],
        variables=[parse_variable(v) for v in data.get("variable", [])],
        tag_manager_url=data.get("tagManagerUrl"),
        raw=data,
    )
