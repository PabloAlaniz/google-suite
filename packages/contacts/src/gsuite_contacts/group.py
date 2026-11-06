"""Contact groups (labels) and the result of an incremental sync."""

from dataclasses import dataclass, field
from typing import Any

from gsuite_contacts.contact import Contact


@dataclass
class ContactGroup:
    """A contact group: one of the user's labels, or a system group like "myContacts"."""

    resource_name: str  # "contactGroups/abc123" or "contactGroups/myContacts"
    name: str
    group_type: str = "USER_CONTACT_GROUP"  # or SYSTEM_CONTACT_GROUP
    member_count: int = 0
    etag: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        """The ID without the "contactGroups/" prefix."""
        return self.resource_name.removeprefix("contactGroups/")

    @property
    def is_system(self) -> bool:
        """myContacts, starred and the like: they can't be renamed or deleted."""
        return self.group_type == "SYSTEM_CONTACT_GROUP"


@dataclass
class ContactsDelta:
    """What changed since a sync token (everything, on the first sync).

    Keep ``sync_token`` and pass it to the next ``Contacts.sync``.
    """

    changed: list[Contact] = field(default_factory=list)
    deleted: list[Contact] = field(default_factory=list)
    sync_token: str | None = None
