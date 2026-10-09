"""Contact entity."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contact:
    """A contact of the user (a People API ``Person`` in the "myContacts" group).

    Only the primary value of single-valued fields is kept; ``emails`` and
    ``phones`` keep every value, primary first. ``raw`` has the full resource.
    """

    resource_name: str  # "people/c123..."
    etag: str | None = None
    display_name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    organization: str | None = None
    job_title: str | None = None
    notes: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def id(self) -> str:
        """The ID without the "people/" prefix."""
        return self.resource_name.removeprefix("people/")

    @property
    def email(self) -> str | None:
        """Primary email."""
        return self.emails[0] if self.emails else None

    @property
    def phone(self) -> str | None:
        """Primary phone number."""
        return self.phones[0] if self.phones else None
