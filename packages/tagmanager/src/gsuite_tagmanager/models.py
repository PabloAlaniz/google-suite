"""Tag Manager entities. Each is addressed by its API ``path`` ("accounts/1/containers/2")."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Account:
    path: str
    account_id: str
    name: str = ""
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Container:
    path: str
    account_id: str
    container_id: str
    name: str = ""
    public_id: str = ""
    """The "GTM-XXXX" id used in the snippet."""
    usage_context: list[str] = field(default_factory=list)
    domain_names: list[str] = field(default_factory=list)
    notes: str | None = None
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Workspace:
    path: str
    workspace_id: str
    name: str = ""
    description: str | None = None
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Tag:
    path: str
    tag_id: str
    name: str = ""
    type: str = ""
    firing_trigger_ids: list[str] = field(default_factory=list)
    blocking_trigger_ids: list[str] = field(default_factory=list)
    paused: bool = False
    parameters: list[dict[str, Any]] = field(default_factory=list)
    """The API's ``parameter`` list, as sent ({"type", "key", "value"/"list"/"map"})."""
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Trigger:
    """A trigger; its conditions (``filter``, ``customEventFilter``...) stay in ``raw``."""

    path: str
    trigger_id: str
    name: str = ""
    type: str = ""
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Variable:
    path: str
    variable_id: str
    name: str = ""
    type: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class VersionHeader:
    """A container version without its contents (see ``TagManager.get_live_version``)."""

    path: str
    container_version_id: str
    name: str = ""
    num_tags: int = 0
    num_triggers: int = 0
    num_variables: int = 0
    deleted: bool = False

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ContainerVersion:
    """A container version with its tags, triggers and variables."""

    path: str
    container_version_id: str
    name: str = ""
    description: str | None = None
    tags: list[Tag] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    tag_manager_url: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
