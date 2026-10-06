"""Drive sharing permissions."""

from dataclasses import dataclass


@dataclass
class Permission:
    """
    Who can access a file and how.

    type is "user", "group", "domain" or "anyone"; role is "reader",
    "commenter", "writer", "fileOrganizer", "organizer" or "owner".
    """

    id: str
    type: str
    role: str
    email_address: str | None = None
    domain: str | None = None
    display_name: str | None = None

    @classmethod
    def from_api(cls, data: dict) -> "Permission":
        return cls(
            id=data["id"],
            type=data.get("type", ""),
            role=data.get("role", ""),
            email_address=data.get("emailAddress"),
            domain=data.get("domain"),
            display_name=data.get("displayName"),
        )
