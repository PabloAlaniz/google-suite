"""Google Suite Tag Manager - read-only GTM v2 client."""

__version__ = "0.1.0"

from gsuite_tagmanager.client import TagManager
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

__all__ = [
    "Account",
    "Container",
    "ContainerVersion",
    "Tag",
    "TagManager",
    "Trigger",
    "Variable",
    "VersionHeader",
    "Workspace",
]
