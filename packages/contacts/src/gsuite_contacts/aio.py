"""Async Contacts: AsyncContacts, the async counterpart of ``Contacts``.

Covers reading (list, search, get, get_many), writing (create, update,
delete), incremental sync and contact groups, with the same arguments and
results as the sync client. Requests go through ``gsuite_core.aio``, so
retries, rate limits and errors are the suite's; bodies and parsing are the
sync client's own code (``gsuite_contacts._requests``).

Example:
    async with AsyncContacts(auth) as contacts:
        delta = await contacts.sync(saved_token)
        for contact in delta.changed:
            ...

Requires ``pip install "gsuite-sdk[async]"``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from gsuite_contacts._requests import (
    BATCH_GET_SIZE,
    MAX_CONTACTS,
    MAX_PAGE_SIZE,
    MAX_SEARCH_RESULTS,
    ContactChanges,
    add_to_delta,
    chunks,
    create_body,
    group_change_bodies,
    group_resource_name,
    is_expired_sync,
    resource_name,
    skipped_members,
    sync_params,
    update_body,
)
from gsuite_contacts.client import SortOrder
from gsuite_contacts.contact import Contact
from gsuite_contacts.group import ContactGroup, ContactsDelta
from gsuite_contacts.parser import GROUP_FIELDS, PERSON_FIELDS, ContactsParser
from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.exceptions import (
    APIError,
    NotFoundError,
    SyncTokenExpiredError,
    ValidationError,
)

API = "https://people.googleapis.com/v1"


class AsyncContacts:
    """Async Google Contacts client (People API).

    Args:
        auth: GoogleAuth with the contacts scope, or google-auth credentials
        person_fields: People API fields to read (see ``Contacts``)
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT)
        transport: httpx transport (tests)
    """

    def __init__(
        self,
        auth: Any,
        person_fields: str = PERSON_FIELDS,
        *,
        timeout: float | None = None,
        transport: Any = None,
    ) -> None:
        self._http = AsyncGoogleClient(auth, timeout=timeout, transport=transport)
        self.person_fields = person_fields
        self._search_warmed_up = False

    async def __aenter__(self) -> AsyncContacts:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        kwargs.setdefault("service", "contacts")
        return await self._http.json(method, f"{API}/{path}", **kwargs)

    # ---- reading ----

    async def iter_contacts(
        self, max_results: int | None = None, sort_order: SortOrder | None = None
    ) -> AsyncIterator[Contact]:
        """Yield the user's contacts, following pagination."""
        params: dict[str, Any] = {"personFields": self.person_fields}
        if sort_order:
            params["sortOrder"] = sort_order
        async for person in self._http.paginate(
            f"{API}/people/me/connections",
            "connections",
            service="contacts",
            params=params,
            max_items=max_results,
            page_size_param="pageSize",
            max_page_size=MAX_PAGE_SIZE,
        ):
            yield ContactsParser.parse_contact(person)

    async def list_contacts(
        self, max_results: int | None = None, sort_order: SortOrder | None = None
    ) -> list[Contact]:
        """The user's contacts."""
        return [c async for c in self.iter_contacts(max_results, sort_order)]

    async def search(self, query: str, max_results: int = 10) -> list[Contact]:
        """Contacts whose names, emails, phones or organizations start with ``query``.

        Sends the People API's cache warm-up (an empty query) once, as ``Contacts`` does.
        """
        if not query.strip():
            raise ValidationError("query", "Search query cannot be empty")
        if not self._search_warmed_up:
            await self._json(
                "GET", "people:searchContacts", params={"query": "", "readMask": self.person_fields}
            )
            self._search_warmed_up = True
        data = await self._json(
            "GET",
            "people:searchContacts",
            params={
                "query": query,
                "readMask": self.person_fields,
                "pageSize": max(1, min(max_results, MAX_SEARCH_RESULTS)),
            },
            resource_type="search",
            resource_id=query,
        )
        return [ContactsParser.parse_contact(r["person"]) for r in data.get("results", [])]

    async def get(self, contact_id: str) -> Contact | None:
        """A contact by ID ("c123" or "people/c123"), or None if it doesn't exist."""
        name = resource_name(contact_id)
        try:
            data = await self._json(
                "GET",
                name,
                params={"personFields": self.person_fields},
                resource_type="contact",
                resource_id=name,
            )
        except NotFoundError:
            return None
        return ContactsParser.parse_contact(data)

    async def get_many(self, contact_ids: list[str]) -> list[Contact]:
        """Several contacts by ID, 200 per request; missing ones are left out."""
        contacts = []
        for chunk in chunks([resource_name(c) for c in contact_ids], BATCH_GET_SIZE):
            data = await self._json(
                "GET",
                "people:batchGet",
                params={"resourceNames": chunk, "personFields": self.person_fields},
                resource_type="contact",
            )
            contacts += [
                ContactsParser.parse_contact(r["person"])
                for r in data.get("responses", [])
                if r.get("person")
            ]
        return contacts

    async def sync(self, sync_token: str | None = None) -> ContactsDelta:
        """Contacts changed or deleted since ``sync_token`` (see ``Contacts.sync``).

        Raises:
            SyncTokenExpiredError: The token is too old; sync again without it.
        """
        params = sync_params(self.person_fields, sync_token)
        delta = ContactsDelta()
        while True:
            try:
                data = await self._json(
                    "GET", "people/me/connections", params=params, resource_type="sync"
                )
            except APIError as exc:
                if is_expired_sync(exc):
                    raise SyncTokenExpiredError("contacts") from exc
                raise
            add_to_delta(delta, data.get("connections", []))
            if not data.get("nextPageToken"):
                delta.sync_token = data.get("nextSyncToken")
                return delta
            params["pageToken"] = data["nextPageToken"]

    # ---- writing ----

    async def create(
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
        """Create a contact (same arguments as ``Contacts.create``)."""
        body = create_body(
            ContactChanges(
                given_name, family_name, emails, phones, organization, job_title, notes, raw_fields
            )
        )
        data = await self._json(
            "POST",
            "people:createContact",
            params={"personFields": self.person_fields},
            json=body,
            resource_type="contact",
        )
        return ContactsParser.parse_contact(data)

    async def update(
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
        """Change fields of a contact (same arguments and rules as ``Contacts.update``).

        Raises:
            NotFoundError: The contact doesn't exist.
        """
        current = await self.get(contact_id)
        if current is None:
            raise NotFoundError("contacts", "contact", contact_id)
        body, update_fields = update_body(
            current,
            ContactChanges(
                given_name, family_name, emails, phones, organization, job_title, notes, raw_fields
            ),
        )
        data = await self._json(
            "PATCH",
            f"{current.resource_name}:updateContact",
            params={"updatePersonFields": update_fields, "personFields": self.person_fields},
            json=body,
            resource_type="contact",
            resource_id=current.resource_name,
        )
        return ContactsParser.parse_contact(data)

    async def delete(self, contact_id: str) -> bool:
        """Delete a contact; False if it didn't exist."""
        name = resource_name(contact_id)
        try:
            await self._json(
                "DELETE", f"{name}:deleteContact", resource_type="contact", resource_id=name
            )
        except NotFoundError:
            return False
        return True

    # ---- groups ----

    async def list_groups(self) -> list[ContactGroup]:
        """The user's contact groups (labels), system groups included."""
        return [
            ContactsParser.parse_group(g)
            async for g in self._http.paginate(
                f"{API}/contactGroups",
                "contactGroups",
                service="contacts",
                params={"groupFields": GROUP_FIELDS},
                page_size_param="pageSize",
                max_page_size=MAX_PAGE_SIZE,
            )
        ]

    async def create_group(self, name: str) -> ContactGroup:
        """Create a contact group (label)."""
        if not name.strip():
            raise ValidationError("name", "A group needs a name")
        data = await self._json(
            "POST",
            "contactGroups",
            json={"contactGroup": {"name": name}, "readGroupFields": GROUP_FIELDS},
            resource_type="group",
            resource_id=name,
        )
        return ContactsParser.parse_group(data)

    async def delete_group(self, group_id: str, delete_contacts: bool = False) -> bool:
        """Delete a group; its contacts stay unless ``delete_contacts``. False if missing."""
        name = group_resource_name(group_id)
        try:
            await self._json(
                "DELETE",
                name,
                params={"deleteContacts": delete_contacts},
                resource_type="group",
                resource_id=name,
            )
        except NotFoundError:
            return False
        return True

    async def group_members(self, group_id: str) -> list[str]:
        """Resource names of every contact in the group."""
        name = group_resource_name(group_id)
        data = await self._json(
            "GET",
            name,
            params={"maxMembers": MAX_CONTACTS, "groupFields": "name"},
            resource_type="group",
            resource_id=name,
        )
        return list(data.get("memberResourceNames", []))

    async def modify_group(
        self, group_id: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> list[str]:
        """Add and remove contacts; returns those Google left as they were."""
        name = group_resource_name(group_id)
        skipped: list[str] = []
        for body in group_change_bodies(add or [], remove or []):
            data = await self._json(
                "POST", f"{name}/members:modify", json=body, resource_type="group", resource_id=name
            )
            skipped += skipped_members(data)
        return skipped
