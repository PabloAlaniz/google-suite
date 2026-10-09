"""Contacts client - high-level interface over the People API."""

import logging
from collections.abc import Iterator
from typing import Any, Literal

from googleapiclient.discovery import build

from gsuite_contacts.contact import Contact
from gsuite_contacts.parser import PERSON_FIELDS, ContactsParser
from gsuite_core import GoogleAuth, authorized_http, execute, paginate
from gsuite_core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

SortOrder = Literal[
    "LAST_MODIFIED_ASCENDING",
    "LAST_MODIFIED_DESCENDING",
    "FIRST_NAME_ASCENDING",
    "LAST_NAME_ASCENDING",
]

MAX_PAGE_SIZE = 1000  # people.connections.list
MAX_SEARCH_RESULTS = 30  # people.searchContacts


def resource_name(contact_id: str) -> str:
    """Accept "c123" or "people/c123"."""
    bare = contact_id.removeprefix("people/")
    if not bare or "/" in bare:
        raise ValidationError("contact_id", f"Invalid contact ID: {contact_id!r}")
    return contact_id if contact_id.startswith("people/") else f"people/{contact_id}"


class Contacts:
    """
    High-level Google Contacts client (People API).

    Example:
        auth = GoogleAuth(scopes=Scopes.contacts())
        auth.authenticate()

        contacts = Contacts(auth)

        for contact in contacts.search("ana"):
            print(contact.display_name, contact.email)

        contact = contacts.create(given_name="Ana", emails=["ana@example.com"])
        contacts.update(contact.id, phones=["+54 11 5555-5555"])
    """

    def __init__(self, auth: GoogleAuth):
        self.auth = auth
        self._service = None
        self._search_warmed_up = False

    @property
    def service(self) -> Any:
        """Lazy-load People API service."""
        if self._service is None:
            self._service = build(
                "people", "v1", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._service

    # ========== Reading ==========

    def iter_contacts(
        self,
        max_results: int | None = None,
        sort_order: SortOrder | None = None,
    ) -> Iterator[Contact]:
        """Iterate over the user's contacts, following pagination."""
        params: dict[str, Any] = {"resourceName": "people/me", "personFields": PERSON_FIELDS}
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
                self.service.people().searchContacts(query="", readMask=PERSON_FIELDS),
                "contacts",
                "search",
                "warmup",
            )
            self._search_warmed_up = True
        data = execute(
            self.service.people().searchContacts(
                query=query,
                readMask=PERSON_FIELDS,
                pageSize=max(1, min(max_results, MAX_SEARCH_RESULTS)),
            ),
            "contacts",
            "search",
            query,
        )
        return [ContactsParser.parse_contact(r["person"]) for r in data.get("results", [])]

    def get(self, contact_id: str) -> Contact | None:
        """A contact by ID ("c123" or "people/c123"), or None if it doesn't exist."""
        name = resource_name(contact_id)
        try:
            data = execute(
                self.service.people().get(resourceName=name, personFields=PERSON_FIELDS),
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
    ) -> Contact:
        """Create a contact. Needs at least a name, an email or a phone."""
        if not (given_name or family_name or emails or phones):
            raise ValidationError("contact", "A contact needs a name, an email or a phone number")
        body, _ = ContactsParser.build_person(
            given_name, family_name, emails, phones, organization, job_title, notes
        )
        data = execute(
            self.service.people().createContact(body=body, personFields=PERSON_FIELDS),
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
    ) -> Contact:
        """Change fields of a contact; fields left as None are kept.

        ``emails`` and ``phones`` replace the whole list ([] clears it).
        Changing the given name keeps the family name and vice versa, and the
        same for organization and job title.

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
        if not fields:
            raise ValidationError("contact", "Nothing to update")
        # The etag makes the update fail instead of overwriting a concurrent change
        body["etag"] = current.etag
        data = execute(
            self.service.people().updateContact(
                resourceName=current.resource_name,
                updatePersonFields=",".join(fields),
                personFields=PERSON_FIELDS,
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
