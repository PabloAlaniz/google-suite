"""Contacts API routes."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import ContactsDep
from gsuite_contacts import Contact

router = APIRouter()

SortOrder = Literal[
    "LAST_MODIFIED_ASCENDING",
    "LAST_MODIFIED_DESCENDING",
    "FIRST_NAME_ASCENDING",
    "LAST_NAME_ASCENDING",
]


class ContactResponse(BaseModel):
    id: str
    resource_name: str
    display_name: str | None
    given_name: str | None
    family_name: str | None
    emails: list[str]
    phones: list[str]
    organization: str | None
    job_title: str | None
    notes: str | None


class ContactRequest(BaseModel):
    given_name: str | None = None
    family_name: str | None = None
    emails: list[EmailStr] | None = Field(None, description="Replaces every email ([] clears)")
    phones: list[str] | None = Field(None, description="Replaces every phone ([] clears)")
    organization: str | None = None
    job_title: str | None = None
    notes: str | None = Field(None, description='"" clears the notes')


def _contact(c: Contact) -> ContactResponse:
    return ContactResponse(
        id=c.id,
        resource_name=c.resource_name,
        display_name=c.display_name,
        given_name=c.given_name,
        family_name=c.family_name,
        emails=c.emails,
        phones=c.phones,
        organization=c.organization,
        job_title=c.job_title,
        notes=c.notes,
    )


def _fields(request: ContactRequest) -> dict[str, Any]:
    fields = request.model_dump()
    if request.emails is not None:
        fields["emails"] = [str(e) for e in request.emails]
    return fields


@router.get("")
def list_contacts(
    contacts: ContactsDep,
    limit: int = Query(100, ge=1, le=2000),
    sort: SortOrder | None = None,
) -> dict[str, Any]:
    """The user's contacts."""
    result = contacts.list_contacts(max_results=limit, sort_order=sort)
    return {"contacts": [_contact(c) for c in result], "count": len(result)}


@router.get("/search")
def search_contacts(
    contacts: ContactsDep,
    q: str = Query(min_length=1, description="Prefix of a name, email, phone or organization"),
    limit: int = Query(10, ge=1, le=30),
) -> dict[str, Any]:
    """Search the user's contacts."""
    result = contacts.search(q, max_results=limit)
    return {"contacts": [_contact(c) for c in result], "count": len(result)}


@router.post("", status_code=201)
def create_contact(request: ContactRequest, contacts: ContactsDep) -> ContactResponse:
    """Create a contact (needs a name, an email or a phone)."""
    return _contact(contacts.create(**_fields(request)))


@router.get("/{contact_id}")
def get_contact(contact_id: str, contacts: ContactsDep) -> ContactResponse:
    """A contact ("c123", without the "people/" prefix)."""
    contact = contacts.get(contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact(contact)


@router.patch("/{contact_id}")
def update_contact(
    contact_id: str, request: ContactRequest, contacts: ContactsDep
) -> ContactResponse:
    """Change a contact; fields not sent (or null) are kept."""
    return _contact(contacts.update(contact_id, **_fields(request)))


@router.delete("/{contact_id}")
def delete_contact(contact_id: str, contacts: ContactsDep) -> dict[str, Any]:
    """Delete a contact."""
    if not contacts.delete(contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"id": contact_id, "status": "deleted"}
