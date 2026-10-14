"""Invariants of ``gsuite_contacts.parser``, shared by property tests and fuzz harnesses."""

from gsuite_contacts.parser import ContactsParser
from gsuite_core._testing import require


def check_person_round_trip(
    given_name: str | None,
    family_name: str | None,
    emails: list[str] | None,
    phones: list[str] | None,
    organization: str | None,
    job_title: str | None,
    notes: str | None,
) -> None:
    """``parse_contact(build_person(...))`` gives back the fields that were set.

    Empty emails/phones are not values, so the parser drops them; empty notes
    are sent as "no biography" (that is how they get cleared).
    """
    body, person_fields = ContactsParser.build_person(
        given_name=given_name,
        family_name=family_name,
        emails=emails,
        phones=phones,
        organization=organization,
        job_title=job_title,
        notes=notes,
    )
    contact = ContactsParser.parse_contact({"resourceName": "people/c1", **body})
    expected = {
        "given_name": given_name,
        "family_name": family_name,
        "emails": [e for e in emails or [] if e],
        "phones": [p for p in phones or [] if p],
        "organization": organization,
        "job_title": job_title,
        "notes": notes or None,
    }
    actual = {name: getattr(contact, name) for name in expected}
    require(actual == expected, f"round trip changed fields: {actual!r} != {expected!r}")
    require(set(person_fields) <= set(body), f"fields {person_fields} not all in the body")
    require(contact.resource_name == "people/c1", "resource name lost")


__all__ = ["check_person_round_trip"]
