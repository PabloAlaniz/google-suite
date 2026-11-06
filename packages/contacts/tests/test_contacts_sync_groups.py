"""Incremental sync, batch get, raw fields and contact groups (mocked People API)."""

import json
from unittest.mock import MagicMock, Mock, patch

import httplib2
import pytest
from googleapiclient.errors import HttpError

from gsuite_contacts import ContactGroup, Contacts
from gsuite_contacts.parser import ContactsParser
from gsuite_core.exceptions import SyncTokenExpiredError, ValidationError


def person(cid, name="Ana", **extra):
    return {"resourceName": f"people/{cid}", "names": [{"displayName": name}], **extra}


def http_error(status, body):
    return HttpError(httplib2.Response({"status": status}), json.dumps(body).encode())


@pytest.fixture
def service():
    with patch("gsuite_core.service.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture
def contacts(service):
    return Contacts(Mock())


def test_parses_urls_groups_and_deletion():
    contact = ContactsParser.parse_contact(
        person(
            "c1",
            urls=[{"value": "https://ana.dev"}],
            memberships=[
                {
                    "contactGroupMembership": {
                        "contactGroupResourceName": "contactGroups/myContacts"
                    }
                },
                {"domainMembership": {"inViewerDomain": True}},
            ],
            metadata={"deleted": True},
        )
    )

    assert contact.urls == ["https://ana.dev"]
    assert contact.groups == ["contactGroups/myContacts"]
    assert contact.deleted is True


class TestSync:
    def test_first_sync_follows_pages_and_keeps_the_token(self, contacts, service):
        lister = service.people().connections().list
        lister.return_value.execute.side_effect = [
            {"connections": [person("c1")], "nextPageToken": "p2"},
            {"connections": [person("c2", "Bea")], "nextSyncToken": "s1"},
        ]

        delta = contacts.sync()

        assert [c.id for c in delta.changed] == ["c1", "c2"]
        assert (delta.deleted, delta.sync_token) == ([], "s1")
        first, second = (c.kwargs for c in lister.call_args_list[-2:])
        assert first["requestSyncToken"] is True
        assert "syncToken" not in first
        assert second["pageToken"] == "p2"

    def test_incremental_sync_separates_deletions(self, contacts, service):
        lister = service.people().connections().list
        lister.return_value.execute.return_value = {
            "connections": [person("c1"), person("c9", metadata={"deleted": True})],
            "nextSyncToken": "s2",
        }

        delta = contacts.sync("s1")

        assert [c.id for c in delta.changed] == ["c1"]
        assert [c.id for c in delta.deleted] == ["c9"]
        assert lister.call_args.kwargs["syncToken"] == "s1"
        assert delta.sync_token == "s2"

    @pytest.mark.parametrize(
        "body",
        [
            {
                "error": {
                    "code": 400,
                    "message": "Sync token is expired. Clear local cache and retry.",
                    "status": "FAILED_PRECONDITION",
                    "details": [{"reason": "EXPIRED_SYNC_TOKEN"}],
                }
            },
            {"error": {"code": 400, "message": "Sync token is expired."}},  # no reason
        ],
    )
    def test_expired_token(self, contacts, service, body):
        execute = service.people().connections().list.return_value.execute
        execute.side_effect = http_error(400, body)

        with pytest.raises(SyncTokenExpiredError):
            contacts.sync("old")


def test_get_many_batches_by_200_and_skips_missing(contacts, service):
    batch = service.people().getBatchGet
    batch.return_value.execute.side_effect = [
        {"responses": [{"person": person(f"c{i}")} for i in range(200)]},
        {"responses": [{"person": person("c200")}, {"status": {"code": 404}}]},
    ]

    found = contacts.get_many([f"c{i}" for i in range(202)])

    assert len(found) == 201
    sizes = [len(c.kwargs["resourceNames"]) for c in batch.call_args_list[-2:]]
    assert sizes == [200, 2]


def test_update_with_raw_fields_adds_them_to_the_mask(contacts, service):
    people = service.people()
    people.get.return_value.execute.return_value = person("c1", etag="e1")
    people.updateContact.return_value.execute.return_value = person("c1")

    contacts.update("c1", raw_fields={"urls": [{"value": "https://ana.dev"}]})

    kwargs = people.updateContact.call_args.kwargs
    assert kwargs["updatePersonFields"] == "urls"
    assert kwargs["body"] == {"urls": [{"value": "https://ana.dev"}], "etag": "e1"}


def test_person_fields_are_configurable(service):
    contacts = Contacts(Mock(), person_fields="names,birthdays")
    service.people().get.return_value.execute.return_value = person("c1")

    contacts.get("c1")

    assert service.people().get.call_args.kwargs["personFields"] == "names,birthdays"


class TestGroups:
    def test_list_and_create(self, contacts, service):
        groups = service.contactGroups()
        groups.list.return_value.execute.return_value = {
            "contactGroups": [
                {
                    "resourceName": "contactGroups/myContacts",
                    "formattedName": "My Contacts",
                    "groupType": "SYSTEM_CONTACT_GROUP",
                    "memberCount": 12,
                },
                {"resourceName": "contactGroups/a1", "name": "Family", "memberCount": 3},
            ]
        }
        groups.create.return_value.execute.return_value = {
            "resourceName": "contactGroups/a2",
            "name": "Work",
        }

        listed = contacts.list_groups()
        created = contacts.create_group("Work")

        assert [(g.name, g.is_system, g.member_count) for g in listed] == [
            ("My Contacts", True, 12),
            ("Family", False, 3),
        ]
        assert created == ContactGroup(
            resource_name="contactGroups/a2", name="Work", raw=created.raw
        )
        assert groups.create.call_args.kwargs["body"]["contactGroup"] == {"name": "Work"}

    def test_members_are_all_requested(self, contacts, service):
        get = service.contactGroups().get
        get.return_value.execute.return_value = {"memberResourceNames": ["people/c1"]}

        assert contacts.group_members("a1") == ["people/c1"]
        assert get.call_args.kwargs["resourceName"] == "contactGroups/a1"
        assert get.call_args.kwargs["maxMembers"] == 25_000

    def test_modify_in_chunks_and_report_skipped(self, contacts, service):
        modify = service.contactGroups().members().modify
        modify.return_value.execute.side_effect = [
            {"notFoundResourceNames": ["people/c5"]},
            {"canNotRemoveLastContactGroupResourceNames": ["people/c7"]},
        ]

        skipped = contacts.modify_group(
            "contactGroups/a1", add=[f"c{i}" for i in range(1500)], remove=["people/c7"]
        )

        assert skipped == ["people/c5", "people/c7"]
        first, second = (c.kwargs["body"] for c in modify.call_args_list[-2:])
        assert len(first["resourceNamesToAdd"]) == 1000
        assert first["resourceNamesToRemove"] == ["people/c7"]
        assert len(second["resourceNamesToAdd"]) == 500
        assert "resourceNamesToRemove" not in second

    def test_delete_keeps_contacts_and_reports_missing(self, contacts, service):
        delete = service.contactGroups().delete
        delete.return_value.execute.side_effect = [
            {},
            http_error(404, {"error": {"code": 404, "message": "nope"}}),
        ]

        assert contacts.delete_group("a1") is True
        assert delete.call_args.kwargs["deleteContacts"] is False
        assert contacts.delete_group("zz") is False

    def test_invalid_ids(self, contacts):
        with pytest.raises(ValidationError):
            contacts.group_members("contactGroups/a/b")
        with pytest.raises(ValidationError):
            contacts.create_group("  ")
