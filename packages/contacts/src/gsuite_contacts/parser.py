"""Convert People API resources to contacts and back."""

from typing import Any

from gsuite_contacts.contact import Contact
from gsuite_contacts.group import ContactGroup

# Person fields read by default (Contacts(person_fields=...) changes them).
PERSON_FIELDS = (
    "names,emailAddresses,phoneNumbers,organizations,biographies,urls,memberships,metadata"
)
GROUP_FIELDS = "name,groupType,memberCount,metadata"


def _primary_first(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda e: not e.get("metadata", {}).get("primary", False))


def _primary(person: dict[str, Any], key: str) -> dict[str, Any]:
    entries = _primary_first(person.get(key, []))
    return entries[0] if entries else {}


def _values(person: dict[str, Any], key: str, field: str) -> list[str]:
    return [e[field] for e in _primary_first(person.get(key, [])) if e.get(field)]


class ContactsParser:
    """Parses People API resources."""

    @staticmethod
    def parse_contact(person: dict[str, Any]) -> Contact:
        """A People API ``Person`` as a Contact (primary values first)."""
        name = _primary(person, "names")
        organization = _primary(person, "organizations")
        return Contact(
            resource_name=person["resourceName"],
            etag=person.get("etag"),
            display_name=name.get("displayName"),
            given_name=name.get("givenName"),
            family_name=name.get("familyName"),
            emails=_values(person, "emailAddresses", "value"),
            phones=_values(person, "phoneNumbers", "value"),
            organization=organization.get("name"),
            job_title=organization.get("title"),
            notes=_primary(person, "biographies").get("value"),
            urls=_values(person, "urls", "value"),
            groups=[
                m["contactGroupMembership"]["contactGroupResourceName"]
                for m in person.get("memberships", [])
                if m.get("contactGroupMembership", {}).get("contactGroupResourceName")
            ],
            deleted=bool(person.get("metadata", {}).get("deleted")),
            raw=person,
        )

    @staticmethod
    def parse_group(group: dict[str, Any]) -> ContactGroup:
        """A People API ``ContactGroup`` (system groups get their formatted name)."""
        return ContactGroup(
            resource_name=group["resourceName"],
            name=group.get("formattedName") or group.get("name", ""),
            group_type=group.get("groupType", "USER_CONTACT_GROUP"),
            member_count=int(group.get("memberCount", 0)),
            etag=group.get("etag"),
            raw=group,
        )

    @staticmethod
    def build_person(
        given_name: str | None = None,
        family_name: str | None = None,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        organization: str | None = None,
        job_title: str | None = None,
        notes: str | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """A Person body with the given fields, and the person fields it sets.

        A field given as "" or [] is sent empty, which clears it on update.
        """
        body: dict[str, Any] = {}
        fields: list[str] = []
        if given_name is not None or family_name is not None:
            name = {}
            if given_name is not None:
                name["givenName"] = given_name
            if family_name is not None:
                name["familyName"] = family_name
            body["names"] = [name]
            fields.append("names")
        if emails is not None:
            body["emailAddresses"] = [{"value": e} for e in emails]
            fields.append("emailAddresses")
        if phones is not None:
            body["phoneNumbers"] = [{"value": p} for p in phones]
            fields.append("phoneNumbers")
        if organization is not None or job_title is not None:
            org = {}
            if organization is not None:
                org["name"] = organization
            if job_title is not None:
                org["title"] = job_title
            body["organizations"] = [org]
            fields.append("organizations")
        if notes is not None:
            body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}] if notes else []
            fields.append("biographies")
        return body, fields
