"""AsyncContacts against a fake People API (httpx.MockTransport)."""

import json
from unittest.mock import patch

import httpx
import pytest

from gsuite_contacts import AsyncContacts
from gsuite_core import Settings
from gsuite_core.exceptions import NotFoundError, SyncTokenExpiredError, ValidationError


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["authorization"] = "Bearer t"


def person(cid, given="Ana", family="Pérez", **extra):
    return {
        "resourceName": f"people/{cid}",
        "etag": f"e-{cid}",
        "names": [{"displayName": f"{given} {family}", "givenName": given, "familyName": family}],
        **extra,
    }


class FakePeopleApi:
    """Answers from ``routes`` keyed by (method, path); records every request."""

    def __init__(self):
        self.calls = []
        self.routes = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1/")
        body = json.loads(request.content) if request.content else None
        params = request.url.params
        self.calls.append((request.method, path, params, body))
        route = self.routes.get((request.method, path))
        if route is None:
            return httpx.Response(404, json={"error": {"code": 404, "message": "not found"}})
        status, payload = route(params, body) if callable(route) else route
        return httpx.Response(status, json=payload)

    def last(self, method, path):
        return next(c for c in reversed(self.calls) if c[:2] == (method, path))


@pytest.fixture(autouse=True)
def settings():
    s = Settings(max_retries=0, _env_file=None)
    with patch("gsuite_core.config.get_settings", return_value=s):
        yield s


@pytest.fixture
def api():
    return FakePeopleApi()


@pytest.fixture
async def contacts(api):
    transport = httpx.MockTransport(api.handler)
    async with AsyncContacts(FakeCredentials(), transport=transport) as client:
        yield client


class TestReading:
    async def test_list_follows_pages(self, contacts, api):
        api.routes["GET", "people/me/connections"] = lambda params, _: (
            (200, {"connections": [person("c2", "Bea")]})
            if params.get("pageToken") == "p2"
            else (200, {"connections": [person("c1")], "nextPageToken": "p2"})
        )

        listed = await contacts.list_contacts(sort_order="FIRST_NAME_ASCENDING")

        assert [c.given_name for c in listed] == ["Ana", "Bea"]
        assert api.calls[0][2]["sortOrder"] == "FIRST_NAME_ASCENDING"

    async def test_search_warms_up_once(self, contacts, api):
        api.routes["GET", "people:searchContacts"] = lambda params, _: (
            200,
            {"results": [{"person": person("c1")}]} if params["query"] else {},
        )

        await contacts.search("ana")
        await contacts.search("bea", max_results=99)

        queries = [c[2]["query"] for c in api.calls]
        assert queries == ["", "ana", "bea"]
        assert api.calls[-1][2]["pageSize"] == "30"

    async def test_get_and_get_many(self, contacts, api):
        api.routes["GET", "people/c1"] = (200, person("c1"))
        api.routes["GET", "people:batchGet"] = lambda params, _: (
            200,
            {
                "responses": [
                    {"person": person(n.removeprefix("people/"))}
                    for n in params.get_list("resourceNames")
                    if n != "people/c999"
                ]
            },
        )

        assert (await contacts.get("c1")).id == "c1"
        assert await contacts.get("c404") is None
        found = await contacts.get_many([f"c{i}" for i in range(201)] + ["c999"])

        assert len(found) == 201  # c999 is missing
        batches = [c for c in api.calls if c[1] == "people:batchGet"]
        assert [len(c[2].get_list("resourceNames")) for c in batches] == [200, 2]


class TestSync:
    async def test_pages_split_deletions_and_keep_the_token(self, contacts, api):
        api.routes["GET", "people/me/connections"] = lambda params, _: (
            (
                200,
                {"connections": [person("c9", metadata={"deleted": True})], "nextSyncToken": "s2"},
            )
            if params.get("pageToken")
            else (200, {"connections": [person("c1")], "nextPageToken": "p2"})
        )

        delta = await contacts.sync("s1")

        assert [c.id for c in delta.changed] == ["c1"]
        assert [c.id for c in delta.deleted] == ["c9"]
        assert delta.sync_token == "s2"
        assert all(c[2]["syncToken"] == "s1" for c in api.calls)
        assert api.calls[0][2]["requestSyncToken"] == "true"

    @pytest.mark.parametrize(
        "error",
        [
            {"code": 400, "message": "Expired", "details": [{"reason": "EXPIRED_SYNC_TOKEN"}]},
            {"code": 400, "message": "Sync token is expired."},
        ],
    )
    async def test_expired_token(self, contacts, api, error):
        api.routes["GET", "people/me/connections"] = (400, {"error": error})

        with pytest.raises(SyncTokenExpiredError):
            await contacts.sync("old")


class TestWriting:
    async def test_create(self, contacts, api):
        api.routes["POST", "people:createContact"] = lambda _, body: (200, person("c5"))

        await contacts.create(given_name="Ana", emails=["a@x.com"], raw_fields={"urls": []})

        assert api.last("POST", "people:createContact")[3] == {
            "names": [{"givenName": "Ana"}],
            "emailAddresses": [{"value": "a@x.com"}],
            "urls": [],
        }
        with pytest.raises(ValidationError):
            await contacts.create(notes="nothing to identify it")

    async def test_update_keeps_the_family_name_and_sends_the_etag(self, contacts, api):
        api.routes["GET", "people/c1"] = (200, person("c1"))
        api.routes["PATCH", "people/c1:updateContact"] = (200, person("c1", "Anita"))

        updated = await contacts.update("c1", given_name="Anita", phones=["+1"])

        _, _, params, body = api.last("PATCH", "people/c1:updateContact")
        assert params["updatePersonFields"] == "names,phoneNumbers"
        assert body["names"] == [{"givenName": "Anita", "familyName": "Pérez"}]
        assert body["etag"] == "e-c1"
        assert updated.given_name == "Anita"

    async def test_update_and_delete_missing(self, contacts, api):
        with pytest.raises(NotFoundError):
            await contacts.update("c404", notes="x")
        assert await contacts.delete("c404") is False


class TestGroups:
    async def test_list_create_delete(self, contacts, api):
        api.routes["GET", "contactGroups"] = (
            200,
            {"contactGroups": [{"resourceName": "contactGroups/a1", "name": "Family"}]},
        )
        api.routes["POST", "contactGroups"] = lambda _, body: (
            200,
            {"resourceName": "contactGroups/a2", "name": body["contactGroup"]["name"]},
        )
        api.routes["DELETE", "contactGroups/a1"] = (200, {})

        assert [g.name for g in await contacts.list_groups()] == ["Family"]
        assert (await contacts.create_group("Work")).id == "a2"
        assert await contacts.delete_group("a1") is True
        assert api.last("DELETE", "contactGroups/a1")[2]["deleteContacts"] == "false"
        assert await contacts.delete_group("zz") is False

    async def test_members_and_modify_in_chunks(self, contacts, api):
        api.routes["GET", "contactGroups/a1"] = (200, {"memberResourceNames": ["people/c1"]})
        api.routes["POST", "contactGroups/a1/members:modify"] = lambda _, body: (
            200,
            {"notFoundResourceNames": ["people/c3"]} if "resourceNamesToRemove" in body else {},
        )

        assert await contacts.group_members("a1") == ["people/c1"]
        assert api.last("GET", "contactGroups/a1")[2]["maxMembers"] == "25000"
        skipped = await contacts.modify_group(
            "a1", add=[f"c{i}" for i in range(1001)], remove=["c3"]
        )

        assert skipped == ["people/c3"]
        sent = [c[3] for c in api.calls if c[1] == "contactGroups/a1/members:modify"]
        assert [len(b.get("resourceNamesToAdd", [])) for b in sent] == [1000, 1]
