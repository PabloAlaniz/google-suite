"""Contacts client - high-level interface over the People API."""

import logging
from collections.abc import Iterator
from http import HTTPStatus
from typing import Any, Literal

from gsuite_contacts.contact import Contact
from gsuite_contacts.group import ContactGroup, ContactsDelta
from gsuite_contacts.parser import GROUP_FIELDS, PERSON_FIELDS, ContactsParser
from gsuite_core import GoogleAuth, execute, paginate
from gsuite_core.exceptions import (
    APIError,
    NotFoundError,
    SyncTokenExpiredError,
    ValidationError,
)
from gsuite_core.service import GoogleService

logger = logging.getLogger(__name__)

SortOrder = Literal[
    "LAST_MODIFIED_ASCENDING",
    "LAST_MODIFIED_DESCENDING",
    "FIRST_NAME_ASCENDING",
    "LAST_NAME_ASCENDING",
]

MAX_PAGE_SIZE = 1000  # people.connections.list
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


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class Contacts:
    """High-level Google Contacts client (People API).

    Example:
        auth = GoogleAuth(scopes=Scopes.contacts())
        auth.authenticate()

        contacts = Contacts(auth)

        for contact in contacts.search("ana"):
            print(contact.display_name, contact.email)

        contact = contacts.create(given_name="Ana", emails=["ana@example.com"])
        contacts.update(contact.id, phones=["+54 11 5555-5555"])
    """

    service = GoogleService("people", "v1")

    def __init__(self, auth: GoogleAuth, person_fields: str = PERSON_FIELDS):
        """Initialize the client.

        Args:
            auth: GoogleAuth with the contacts scope
            person_fields: People API fields to read (comma-separated); add
                e.g. "addresses,birthdays" and find them in ``Contact.raw``
        """
        self.auth = auth
        self.person_fields = person_fields
        self._search_warmed_up = False

    # ========== Reading ==========

    def iter_contacts(
        self,
        max_results: int | None = None,
        sort_order: SortOrder | None = None,
    ) -> Iterator[Contact]:
        """Iterate over the user's contacts, following pagination."""
        params: dict[str, Any] = {"resourceName": "people/me", "personFields": self.person_fields}
        if sort_order:
            params["sortOrder"] = sort_order
        for person in paginate(
            self.service.people().connections().list,
            "connections",
            "contacts",
            max_items=max_results,
            page_size_param="pageSize",
            max_page_size=MAX_PAGE_SIZE,
            **params,
        ):
            yield ContactsParser.parse_contact(person)

    def list_contacts(self, max_results: int | None = None, **kwargs: Any) -> list[Contact]:
        """The user's contacts (see ``iter_contacts``)."""
        return list(self.iter_contacts(max_results, **kwargs))

    def search(self, query: str, max_results: int = 10) -> list[Contact]:
        """Contacts whose names, emails, phones or organizations start with ``query``.

        The People API serves searches from a cache that a first, empty query
        warms up; without it the first results can be stale or empty. The
        client sends that warm-up once.
        """
        if not query.strip():
            raise ValidationError("query", "Search query cannot be empty")
        if not self._search_warmed_up:
            execute(
                self.service.people().searchContacts(query="", readMask=self.person_fields),
                "contacts",
                "search",
                "warmup",
            )
            self._search_warmed_up = True
        data = execute(
            self.service.people().searchContacts(
                query=query,
                readMask=self.person_fields,
                pageSize=max(1, min(max_results, MAX_SEARCH_RESULTS)),
            ),
            "contacts",
            "search",
            query,
        )
        return [ContactsParser.parse_contact(r["person"]) for r in data.get("results", [])]

    def sync(self, sync_token: str | None = None) -> ContactsDelta:
        """Contacts changed or deleted since ``sync_token`` (all contacts without one).

        Keep ``delta.sync_token`` for the next call. The first sync lists
        every contact; later ones return only what changed, deleted contacts
        included (``Contact.deleted``).

        Raises:
            SyncTokenExpiredError: The token is too old (about 7 days) or
                was issued for other person fields; sync again without it.
        """
        params: dict[str, Any] = {
            "resourceName": "people/me",
            "personFields": self.person_fields,
            "pageSize": MAX_PAGE_SIZE,
            "requestSyncToken": True,
        }
        if sync_token:
            params["syncToken"] = sync_token
        delta = ContactsDelta()
        while True:
            try:
                data = execute(
                    self.service.people().connections().list(**params), "contacts", "sync"
                )
            except APIError as exc:
                # Older error bodies say so only in the message
                if (
                    exc.status_code == HTTPStatus.BAD_REQUEST
                    and "sync token" in exc.message.lower()
                ):
                    raise SyncTokenExpiredError("contacts") from exc
                raise
            for person in data.get("connections", []):
                contact = ContactsParser.parse_contact(person)
                (delta.deleted if contact.deleted else delta.changed).append(contact)
            if not data.get("nextPageToken"):
                delta.sync_token = data.get("nextSyncToken")
                return delta
            params["pageToken"] = data["nextPageToken"]

    def get_many(self, contact_ids: list[str]) -> list[Contact]:
        """Several contacts by ID, 200 per request; missing ones are left out."""
        names = [resource_name(c) for c in contact_ids]
        contacts = []
        for chunk in _chunks(names, BATCH_GET_SIZE):
            data = execute(
                self.service.people().getBatchGet(
                    resourceNames=chunk, personFields=self.person_fields
                ),
                "contacts",
                "contact",
            )
            contacts += [
                ContactsParser.parse_contact(r["person"])
                for r in data.get("responses", [])
                if r.get("person")
            ]
        return contacts

    def get(self, contact_id: str) -> Contact | None:
        """A contact by ID ("c123" or "people/c123"), or None if it doesn't exist."""
        name = resource_name(contact_id)
        try:
            data = execute(
                self.service.people().get(resourceName=name, personFields=self.person_fields),
                "contacts",
                "contact",
                name,
            )
        except NotFoundError:
            return None
        return ContactsParser.parse_contact(data)

    # ========== Writing ==========

    def create(
        self,
        given_name: str | None = None,
        family_name: str | None = None,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        organization: str | None = None,
        job_title: str | None = None,
        notes: str | None = None,
        raw_fields: dict[str, Any] | None = None,
    ) -> Contact:
        """Create a contact. Needs at least a name, an email or a phone.

        Args:
            given_name: First name
            family_name: Last name
            emails: Email addresses, primary first
            phones: Phone numbers, primary first
            organization: Company
            job_title: Title at the company
            notes: Free text ("biographies" in the API)
            raw_fields: More Person fields as the API takes them, e.g.
                {"urls": [{"value": "https://..."}], "birthdays": [...]}
        """
        if not (given_name or family_name or emails or phones):
            raise ValidationError("contact", "A contact needs a name, an email or a phone number")
        body, _ = ContactsParser.build_person(
            given_name, family_name, emails, phones, organization, job_title, notes
        )
        body.update(raw_fields or {})
        data = execute(
            self.service.people().createContact(body=body, personFields=self.person_fields),
            "contacts",
            "contact",
            given_name or (emails or phones or [""])[0],
        )
        return ContactsParser.parse_contact(data)

    def update(
        self,
        contact_id: str,
        given_name: str | None = None,
        family_name: str | None = None,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        organization: str | None = None,
        job_title: str | None = None,
        notes: str | None = None,
        raw_fields: dict[str, Any] | None = None,
    ) -> Contact:
        """Change fields of a contact; fields left as None are kept.

        ``emails`` and ``phones`` replace the whole list ([] clears it).
        Changing the given name keeps the family name and vice versa, and the
        same for organization and job title. ``raw_fields`` sets any other
        Person field as the API takes it (each replaces that whole field),
        e.g. {"urls": [{"value": "https://..."}]}.

        Raises:
            NotFoundError: The contact doesn't exist.
        """
        current = self.get(contact_id)
        if current is None:
            raise NotFoundError("contacts", "contact", contact_id)

        if given_name is not None or family_name is not None:
            given_name = current.given_name if given_name is None else given_name
            family_name = current.family_name if family_name is None else family_name
        if organization is not None or job_title is not None:
            organization = current.organization if organization is None else organization
            job_title = current.job_title if job_title is None else job_title
        body, fields = ContactsParser.build_person(
            given_name, family_name, emails, phones, organization, job_title, notes
        )
        body.update(raw_fields or {})
        fields += [f for f in raw_fields or {} if f not in fields]
        if not fields:
            raise ValidationError("contact", "Nothing to update")
        # The etag makes the update fail instead of overwriting a concurrent change
        body["etag"] = current.etag
        data = execute(
            self.service.people().updateContact(
                resourceName=current.resource_name,
                updatePersonFields=",".join(fields),
                personFields=self.person_fields,
                body=body,
            ),
            "contacts",
            "contact",
            current.resource_name,
        )
        return ContactsParser.parse_contact(data)

    def delete(self, contact_id: str) -> bool:
        """Delete a contact. False if it didn't exist."""
        name = resource_name(contact_id)
        try:
            execute(
                self.service.people().deleteContact(resourceName=name),
                "contacts",
                "contact",
                name,
            )
        except NotFoundError:
            return False
        return True

    # ========== Groups ==========

    def list_groups(self) -> list[ContactGroup]:
        """The user's contact groups (labels), system groups included."""
        return [
            ContactsParser.parse_group(g)
            for g in paginate(
                self.service.contactGroups().list,
                "contactGroups",
                "contacts",
                page_size_param="pageSize",
                max_page_size=MAX_PAGE_SIZE,
                groupFields=GROUP_FIELDS,
            )
        ]

    def create_group(self, name: str) -> ContactGroup:
        """Create a contact group (label)."""
        if not name.strip():
            raise ValidationError("name", "A group needs a name")
        data = execute(
            self.service.contactGroups().create(
                body={"contactGroup": {"name": name}, "readGroupFields": GROUP_FIELDS}
            ),
            "contacts",
            "group",
            name,
        )
        return ContactsParser.parse_group(data)

    def delete_group(self, group_id: str, delete_contacts: bool = False) -> bool:
        """Delete a group; its contacts stay unless ``delete_contacts``. False if missing."""
        name = group_resource_name(group_id)
        try:
            execute(
                self.service.contactGroups().delete(
                    resourceName=name, deleteContacts=delete_contacts
                ),
                "contacts",
                "group",
                name,
            )
        except NotFoundError:
            return False
        return True

    def group_members(self, group_id: str) -> list[str]:
        """Resource names ("people/c...") of the group's contacts, all of them."""
        name = group_resource_name(group_id)
        data = execute(
            self.service.contactGroups().get(
                resourceName=name, maxMembers=MAX_CONTACTS, groupFields="name"
            ),
            "contacts",
            "group",
            name,
        )
        return list(data.get("memberResourceNames", []))

    def modify_group(
        self, group_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> list[str]:
        """Add contacts to a group and remove others (IDs or resource names).

        Returns:
            Contacts Google didn't find, or couldn't remove because the group
            is their last one; the rest were changed
        """
        name = group_resource_name(group_id)
        to_add = [resource_name(c) for c in add or []]
        to_remove = [resource_name(c) for c in remove or []]
        skipped: list[str] = []
        while to_add or to_remove:
            body: dict[str, Any] = {}
            if to_add:
                body["resourceNamesToAdd"] = to_add[:MAX_GROUP_CHANGES]
                to_add = to_add[MAX_GROUP_CHANGES:]
            if to_remove:
                body["resourceNamesToRemove"] = to_remove[:MAX_GROUP_CHANGES]
                to_remove = to_remove[MAX_GROUP_CHANGES:]
            data = execute(
                self.service.contactGroups().members().modify(resourceName=name, body=body),
                "contacts",
                "group",
                name,
            )
            skipped += data.get("notFoundResourceNames", [])
            skipped += data.get("canNotRemoveLastContactGroupResourceNames", [])
        return skipped
