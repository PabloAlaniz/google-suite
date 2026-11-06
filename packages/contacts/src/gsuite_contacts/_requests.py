"""Request bodies and parameters for the People API, shared by the sync and async clients."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from gsuite_contacts.contact import Contact
from gsuite_contacts.group import ContactsDelta
from gsuite_contacts.parser import ContactsParser
from gsuite_core.exceptions import APIError, ValidationError

MAX_PAGE_SIZE = 1000  # people.connections.list, contactGroups.list
MAX_SEARCH_RESULTS = 30  # people.searchContacts
BATCH_GET_SIZE = 200  # people.getBatchGet
MAX_GROUP_CHANGES = 1000  # contactGroups.members.modify, per list
MAX_CONTACTS = 25_000  # a Google account holds at most this many contacts


def resource_name(contact_id: str) -> str:
    """Accept "c123" or "people/c123"."""
    bare = contact_id.removeprefix("people/")
    if not bare or "/" in bare:
        raise ValidationError("contact_id", f"Invalid contact ID: {contact_id!r}")
    return contact_id if contact_id.startswith("people/") else f"people/{contact_id}"


def group_resource_name(group_id: str) -> str:
    """Accept "abc123", "myContacts" or "contactGroups/abc123"."""
    bare = group_id.removeprefix("contactGroups/")
    if not bare or "/" in bare:
        raise ValidationError("group_id", f"Invalid group ID: {group_id!r}")
    return f"contactGroups/{bare}"


def chunks(items: list[str], size: int) -> list[list[str]]:
    """``items`` in lists of at most ``size``."""
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True)
class ContactChanges:
    """The fields to set on a contact; None leaves a field as it is."""

    given_name: str | None = None
    family_name: str | None = None
    emails: list[str] | None = None
    phones: list[str] | None = None
    organization: str | None = None
    job_title: str | None = None
    notes: str | None = None
    raw_fields: dict[str, Any] | None = None

    def person_body(self) -> tuple[dict[str, Any], list[str]]:
        """A Person body with these fields, and the person fields it sets."""
        body, fields = ContactsParser.build_person(
            self.given_name,
            self.family_name,
            self.emails,
            self.phones,
            self.organization,
            self.job_title,
            self.notes,
        )
        body.update(self.raw_fields or {})
        fields += [f for f in self.raw_fields or {} if f not in fields]
        return body, fields


IDENTIFYING_FIELDS = ("names", "emailAddresses", "phoneNumbers")


def create_body(changes: ContactChanges) -> dict[str, Any]:
    """people.createContact body; a contact needs a name, an email or a phone.

    They can come as arguments or already in API form in ``raw_fields``.
    """
    body = changes.person_body()[0]
    filled = (
        value
        for key in IDENTIFYING_FIELDS
        for entry in body.get(key) or []
        for name, value in entry.items()
        if name != "metadata"
    )
    if not any(filled):
        raise ValidationError("contact", "A contact needs a name, an email or a phone number")
    return body


def raw_update(body: dict[str, Any], update_fields: str | list[str]) -> tuple[dict[str, Any], str]:
    """(body, updatePersonFields) for an update sent as given; the body needs its etag."""
    if not body.get("etag"):
        raise ValidationError("etag", "a raw update needs the contact's etag")
    fields = update_fields if isinstance(update_fields, str) else ",".join(update_fields)
    if not fields:
        raise ValidationError("update_fields", "say which person fields to update")
    return body, fields


def update_body(current: Contact, changes: ContactChanges) -> tuple[dict[str, Any], str]:
    """(body, updatePersonFields) for people.updateContact.

    Changing the given name keeps the family name and vice versa, and the same
    for organization and job title. The etag makes the update fail instead of
    overwriting a concurrent change.
    """
    given, family = changes.given_name, changes.family_name
    if given is not None or family is not None:
        given = current.given_name if given is None else given
        family = current.family_name if family is None else family
    organization, title = changes.organization, changes.job_title
    if organization is not None or title is not None:
        organization = current.organization if organization is None else organization
        title = current.job_title if title is None else title
    merged = ContactChanges(
        given,
        family,
        changes.emails,
        changes.phones,
        organization,
        title,
        changes.notes,
        changes.raw_fields,
    )
    body, fields = merged.person_body()
    if not fields:
        raise ValidationError("contact", "Nothing to update")
    body["etag"] = current.etag
    return body, ",".join(fields)


def sync_params(person_fields: str, sync_token: str | None) -> dict[str, Any]:
    """people.connections.list parameters for a sync (paging aside)."""
    params: dict[str, Any] = {
        "personFields": person_fields,
        "pageSize": MAX_PAGE_SIZE,
        "requestSyncToken": True,
    }
    if sync_token:
        params["syncToken"] = sync_token
    return params


def is_expired_sync(exc: APIError) -> bool:
    """An expired-token error from an older body that carries no reason, only a message."""
    return exc.status_code == HTTPStatus.BAD_REQUEST and "sync token" in exc.message.lower()


def add_to_delta(delta: ContactsDelta, people: list[dict[str, Any]]) -> None:
    """Sort a sync page's people into changed and deleted."""
    for person in people:
        contact = ContactsParser.parse_contact(person)
        (delta.deleted if contact.deleted else delta.changed).append(contact)


def group_change_bodies(add: list[str], remove: list[str]) -> list[dict[str, Any]]:
    """contactGroups.members.modify bodies, at most 1000 IDs per list each."""
    to_add = [resource_name(c) for c in add]
    to_remove = [resource_name(c) for c in remove]
    bodies = []
    while to_add or to_remove:
        body: dict[str, Any] = {}
        if to_add:
            body["resourceNamesToAdd"], to_add = (
                to_add[:MAX_GROUP_CHANGES],
                to_add[MAX_GROUP_CHANGES:],
            )
        if to_remove:
            body["resourceNamesToRemove"], to_remove = (
                to_remove[:MAX_GROUP_CHANGES],
                to_remove[MAX_GROUP_CHANGES:],
            )
        bodies.append(body)
    return bodies


def skipped_members(response: dict[str, Any]) -> list[str]:
    """Contacts a members.modify call left as they were."""
    return [
        *response.get("notFoundResourceNames", []),
        *response.get("canNotRemoveLastContactGroupResourceNames", []),
    ]
