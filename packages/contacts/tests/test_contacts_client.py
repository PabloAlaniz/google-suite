"""Contacts client against a mocked People API service."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_contacts import Contact, Contacts
from gsuite_contacts.client import resource_name
from gsuite_contacts.parser import PERSON_FIELDS, ContactsParser
from gsuite_core.exceptions import NotFoundError, ValidationError

PERSON = {
    "resourceName": "people/c1",
    "etag": "e1",
    "names": [
        {"displayName": "Ana Pérez", "givenName": "Ana", "familyName": "Pérez"},
    ],
    "emailAddresses": [
        {"value": "ana@work.com"},
        {"value": "ana@home.com", "metadata": {"primary": True}},
    ],
    "phoneNumbers": [{"value": "+54 11 5555-5555"}],
    "organizations": [{"name": "Acme", "title": "CTO"}],
    "biographies": [{"value": "Met at PyCon"}],
}


@pytest.fixture
def service():
    with patch("gsuite_contacts.client.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture
def people(service):
    return service.people()


@pytest.fixture
def contacts(service):
    return Contacts(Mock())


class TestParsing:
    def test_parse(self):
        contact = ContactsParser.parse_contact(PERSON)

        assert contact == Contact(
            resource_name="people/c1",
            etag="e1",
            display_name="Ana Pérez",
            given_name="Ana",
            family_name="Pérez",
            emails=["ana@home.com", "ana@work.com"],  # primary first
            phones=["+54 11 5555-5555"],
            organization="Acme",
            job_title="CTO",
            notes="Met at PyCon",
            raw=PERSON,
        )
        assert contact.id == "c1"
        assert contact.email == "ana@home.com"
        assert contact.phone == "+54 11 5555-5555"

    def test_parse_empty_person(self):
        contact = ContactsParser.parse_contact({"resourceName": "people/c2"})
        assert contact.display_name is None
        assert contact.email is None
        assert contact.phone is None

    def test_build_person(self):
        body, fields = ContactsParser.build_person(
            given_name="Ana", emails=["a@x.com"], job_title="CTO", notes=""
        )
        assert body == {
            "names": [{"givenName": "Ana"}],
            "emailAddresses": [{"value": "a@x.com"}],
            "organizations": [{"title": "CTO"}],
            "biographies": [],  # "" clears the notes
        }
        assert fields == ["names", "emailAddresses", "organizations", "biographies"]

    @pytest.mark.parametrize(
        ("value", "expected"), [("c1", "people/c1"), ("people/c1", "people/c1")]
    )
    def test_resource_name(self, value, expected):
        assert resource_name(value) == expected

    @pytest.mark.parametrize("value", ["", "people/", "contactGroups/x", "people/c1/x"])
    def test_bad_resource_name(self, value):
        with pytest.raises(ValidationError):
            resource_name(value)


class TestRead:
    def test_list_follows_pages(self, contacts, people):
        people.connections().list().execute.side_effect = [
            {"connections": [PERSON], "nextPageToken": "p2"},
            {"connections": [{"resourceName": "people/c2"}]},
        ]

        result = contacts.list_contacts(sort_order="LAST_NAME_ASCENDING")

        assert [c.id for c in result] == ["c1", "c2"]
        assert people.connections().list.call_args.kwargs == {
            "resourceName": "people/me",
            "personFields": PERSON_FIELDS,
            "sortOrder": "LAST_NAME_ASCENDING",
            "pageSize": 1000,
            "pageToken": "p2",
        }

    def test_list_max_results(self, contacts, people):
        people.connections().list().execute.return_value = {"connections": [PERSON] * 3}
        assert len(contacts.list_contacts(max_results=2)) == 2
        assert people.connections().list.call_args.kwargs["pageSize"] == 2

    def test_search_warms_up_once(self, contacts, people):
        people.searchContacts().execute.return_value = {"results": [{"person": PERSON}]}
        people.searchContacts.reset_mock()

        assert contacts.search("ana")[0].given_name == "Ana"
        contacts.search("pérez", max_results=100)

        calls = [c.kwargs for c in people.searchContacts.call_args_list]
        assert calls[0] == {"query": "", "readMask": PERSON_FIELDS}
        assert calls[1]["query"] == "ana"
        assert calls[2]["pageSize"] == 30  # the API's maximum
        assert len(calls) == 3

    def test_search_no_results(self, contacts, people):
        people.searchContacts().execute.return_value = {}
        assert contacts.search("zz") == []

    def test_search_requires_query(self, contacts):
        with pytest.raises(ValidationError):
            contacts.search(" ")

    def test_get(self, contacts, people):
        people.get().execute.return_value = PERSON
        assert contacts.get("c1").display_name == "Ana Pérez"
        people.get.assert_called_with(resourceName="people/c1", personFields=PERSON_FIELDS)

    def test_get_missing(self, contacts, people, http_error):
        people.get().execute.side_effect = http_error(404)
        assert contacts.get("c9") is None


class TestWrite:
    def test_create(self, contacts, people):
        people.createContact().execute.return_value = PERSON

        contact = contacts.create(given_name="Ana", family_name="Pérez", emails=["ana@home.com"])

        assert contact.id == "c1"
        people.createContact.assert_called_with(
            body={
                "names": [{"givenName": "Ana", "familyName": "Pérez"}],
                "emailAddresses": [{"value": "ana@home.com"}],
            },
            personFields=PERSON_FIELDS,
        )

    def test_create_needs_something(self, contacts):
        with pytest.raises(ValidationError):
            contacts.create(organization="Acme")

    def test_update_keeps_the_other_half_and_sends_etag(self, contacts, people):
        people.get().execute.return_value = PERSON
        people.updateContact().execute.return_value = PERSON

        contacts.update("c1", given_name="Anita", job_title="CEO", phones=[])

        kwargs = people.updateContact.call_args.kwargs
        assert kwargs["resourceName"] == "people/c1"
        assert kwargs["updatePersonFields"] == "names,phoneNumbers,organizations"
        assert kwargs["body"] == {
            "names": [{"givenName": "Anita", "familyName": "Pérez"}],
            "phoneNumbers": [],
            "organizations": [{"name": "Acme", "title": "CEO"}],
            "etag": "e1",
        }

    def test_update_missing(self, contacts, people, http_error):
        people.get().execute.side_effect = http_error(404)
        with pytest.raises(NotFoundError):
            contacts.update("c9", given_name="x")

    def test_update_nothing(self, contacts, people):
        people.get().execute.return_value = PERSON
        with pytest.raises(ValidationError):
            contacts.update("c1")

    def test_delete(self, contacts, people, http_error):
        assert contacts.delete("people/c1") is True
        people.deleteContact.assert_called_with(resourceName="people/c1")
        people.deleteContact().execute.side_effect = http_error(404)
        assert contacts.delete("c1") is False
