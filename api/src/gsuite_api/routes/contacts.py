"""Contacts API routes."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from gsuite_api.dependencies import ContactsDep
from gsuite_contacts import Contact, ContactGroup

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
    urls: list[str]
    groups: list[str]


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
        urls=c.urls,
        groups=c.groups,
    )


class GroupResponse(BaseModel):
    """A contact group (label)."""

    id: str
    resource_name: str
    name: str
    group_type: str
    member_count: int


class CreateGroupRequest(BaseModel):
    """Name of the group to create."""

    name: str = Field(..., min_length=1)


class ModifyGroupRequest(BaseModel):
    """Contacts to add to the group and to remove from it."""

    add: list[str] = Field(default_factory=list, description="Contact IDs to add")
    remove: list[str] = Field(default_factory=list, description="Contact IDs to remove")


class SyncRequest(BaseModel):
    """Where the previous sync left off."""

    sync_token: str | None = Field(
        None, description="From the previous sync; omit to list every contact"
    )


def _group(g: ContactGroup) -> GroupResponse:
    return GroupResponse(
        id=g.id,
        resource_name=g.resource_name,
        name=g.name,
        group_type=g.group_type,
        member_count=g.member_count,
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


@router.post("/sync")
def sync_contacts(request: SyncRequest, contacts: ContactsDep) -> dict[str, Any]:
    """Contacts changed or deleted since `sync_token` (every contact without one).

    Keep the returned `sync_token` for the next call. An expired token is a 410:
    sync again without it.
    """
    delta = contacts.sync(request.sync_token)
    return {
        "changed": [_contact(c) for c in delta.changed],
        "deleted": [c.id for c in delta.deleted],
        "sync_token": delta.sync_token,
    }


@router.get("/groups")
def list_groups(contacts: ContactsDep) -> dict[str, Any]:
    """Contact groups (labels), system groups included."""
    groups = contacts.list_groups()
    return {"groups": [_group(g) for g in groups], "count": len(groups)}


@router.post("/groups", status_code=201)
def create_group(request: CreateGroupRequest, contacts: ContactsDep) -> GroupResponse:
    """Create a contact group."""
    return _group(contacts.create_group(request.name))


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: str, contacts: ContactsDep, delete_contacts: bool = False
) -> dict[str, Any]:
    """Delete a group; its contacts stay unless delete_contacts=true."""
    if not contacts.delete_group(group_id, delete_contacts=delete_contacts):
        raise HTTPException(status_code=404, detail="Group not found")
    return {"id": group_id, "status": "deleted"}


@router.get("/groups/{group_id}/members")
def group_members(group_id: str, contacts: ContactsDep) -> dict[str, Any]:
    """IDs of every contact in the group."""
    members = [m.removeprefix("people/") for m in contacts.group_members(group_id)]
    return {"members": members, "count": len(members)}


@router.post("/groups/{group_id}/members")
def modify_group(
    group_id: str, request: ModifyGroupRequest, contacts: ContactsDep
) -> dict[str, Any]:
    """Add and remove contacts; `skipped` lists those Google left as they were."""
    skipped = contacts.modify_group(group_id, add=request.add, remove=request.remove)
    return {"status": "success", "skipped": [s.removeprefix("people/") for s in skipped]}


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
