"""Tasks and Contacts REST routes with mocked clients."""

from datetime import UTC, date, datetime

import pytest

from gsuite_contacts import Contact
from gsuite_core.exceptions import NotFoundError, ValidationError
from gsuite_tasks import Task, TaskList


def _task(**overrides) -> Task:
    fields = {
        "id": "t1",
        "title": "Pay rent",
        "tasklist_id": "@default",
        "due": date(2026, 2, 1),
        "updated": datetime(2026, 1, 20, tzinfo=UTC),
    }
    fields.update(overrides)
    return Task(**fields)


@pytest.fixture
def tasks(services):
    return services["tasks"]


@pytest.fixture
def contacts(services):
    return services["contacts"]


class TestTaskLists:
    def test_list(self, client, tasks):
        tasks.list_tasklists.return_value = [TaskList(id="l1", title="Inbox")]
        body = client.get("/tasks/lists").json()
        assert body == {"tasklists": [{"id": "l1", "title": "Inbox", "updated": None}], "count": 1}

    def test_create_get_rename(self, client, tasks):
        tasks.create_tasklist.return_value = TaskList(id="l1", title="Home")
        response = client.post("/tasks/lists", json={"title": "Home"})
        assert response.status_code == 201
        assert client.post("/tasks/lists", json={"title": ""}).status_code == 422

        tasks.get_tasklist.return_value = None
        assert client.get("/tasks/lists/nope").status_code == 404

        tasks.rename_tasklist.return_value = TaskList(id="l1", title="House")
        assert client.patch("/tasks/lists/l1", json={"title": "House"}).json()["title"] == "House"

    def test_delete(self, client, tasks):
        tasks.delete_tasklist.return_value = True
        assert client.delete("/tasks/lists/l1").json()["status"] == "deleted"
        tasks.delete_tasklist.return_value = False
        assert client.delete("/tasks/lists/l1").status_code == 404

    def test_clear(self, client, tasks):
        assert client.post("/tasks/lists/@default:clear").json()["status"] == "cleared"
        tasks.clear_completed.assert_called_once_with("@default")


class TestTasks:
    def test_list_with_filters(self, client, tasks):
        tasks.list_tasks.return_value = [_task()]

        response = client.get(
            "/tasks/lists/@default/tasks",
            params={"show_completed": "false", "due_max": "2026-02-28", "limit": 5},
        )

        body = response.json()
        assert body["count"] == 1
        assert body["tasks"][0]["due"] == "2026-02-01"
        assert body["tasks"][0]["completed"] is False
        tasks.list_tasks.assert_called_once_with(
            "@default",
            show_completed=False,
            show_hidden=False,
            due_min=None,
            due_max=date(2026, 2, 28),
            max_results=5,
        )

    def test_create(self, client, tasks):
        tasks.create_task.return_value = _task()

        response = client.post(
            "/tasks/lists/work/tasks", json={"title": "Pay rent", "due": "2026-02-01"}
        )

        assert response.status_code == 201
        tasks.create_task.assert_called_once_with(
            "Pay rent",
            notes=None,
            due=date(2026, 2, 1),
            tasklist_id="work",
            parent=None,
            previous=None,
        )

    def test_get_missing(self, client, tasks):
        tasks.get_task.return_value = None
        assert client.get("/tasks/lists/l/tasks/nope").status_code == 404

    def test_update_sends_only_sent_fields(self, client, tasks):
        tasks.update_task.return_value = _task(notes=None)

        client.patch("/tasks/lists/l/tasks/t1", json={"notes": None})

        # notes sent as null clears them; due was not sent and is left alone
        tasks.update_task.assert_called_once_with("t1", tasklist_id="l", notes=None)

    def test_complete_and_reopen(self, client, tasks):
        tasks.complete_task.return_value = _task(status="completed")
        tasks.reopen_task.return_value = _task()

        done = client.patch("/tasks/lists/l/tasks/t1", json={"completed": True}).json()
        assert done["completed"] is True
        tasks.update_task.assert_not_called()

        client.patch("/tasks/lists/l/tasks/t1", json={"completed": False, "title": "Again"})
        tasks.update_task.assert_called_once_with("t1", tasklist_id="l", title="Again")
        tasks.reopen_task.assert_called_once_with("t1", tasklist_id="l")

    def test_update_nothing(self, client):
        assert client.patch("/tasks/lists/l/tasks/t1", json={}).status_code == 422

    def test_move(self, client, tasks):
        tasks.move_task.return_value = _task(parent="p")
        body = client.post("/tasks/lists/l/tasks/t1:move", json={"parent": "p"}).json()
        assert body["parent"] == "p"
        tasks.move_task.assert_called_once_with("t1", tasklist_id="l", parent="p", previous=None)

    def test_delete(self, client, tasks):
        tasks.delete_task.return_value = False
        assert client.delete("/tasks/lists/l/tasks/t1").status_code == 404


def _contact(**overrides) -> Contact:
    fields = {
        "resource_name": "people/c1",
        "display_name": "Ana Pérez",
        "given_name": "Ana",
        "emails": ["ana@example.com"],
    }
    fields.update(overrides)
    return Contact(**fields)


class TestContacts:
    def test_list(self, client, contacts):
        contacts.list_contacts.return_value = [_contact()]

        body = client.get("/contacts", params={"sort": "LAST_NAME_ASCENDING"}).json()

        assert body["count"] == 1
        assert body["contacts"][0]["id"] == "c1"
        contacts.list_contacts.assert_called_once_with(
            max_results=100, sort_order="LAST_NAME_ASCENDING"
        )

    def test_search(self, client, contacts):
        contacts.search.return_value = [_contact()]
        assert client.get("/contacts/search", params={"q": "ana"}).json()["count"] == 1
        contacts.search.assert_called_once_with("ana", max_results=10)
        assert client.get("/contacts/search").status_code == 422

    def test_get(self, client, contacts):
        contacts.get.return_value = _contact()
        assert client.get("/contacts/c1").json()["emails"] == ["ana@example.com"]
        contacts.get.return_value = None
        assert client.get("/contacts/c9").status_code == 404

    def test_create(self, client, contacts):
        contacts.create.return_value = _contact()

        response = client.post(
            "/contacts", json={"given_name": "Ana", "emails": ["ana@example.com"]}
        )

        assert response.status_code == 201
        kwargs = contacts.create.call_args.kwargs
        assert kwargs["emails"] == ["ana@example.com"]
        assert kwargs["phones"] is None
        assert client.post("/contacts", json={"emails": ["not-an-email"]}).status_code == 422

    def test_create_without_identity_is_422(self, client, contacts):
        contacts.create.side_effect = ValidationError("contact", "needs a name")
        assert client.post("/contacts", json={"organization": "Acme"}).status_code == 422

    def test_update_missing_is_404(self, client, contacts):
        contacts.update.side_effect = NotFoundError("contacts", "contact", "c9")
        assert client.patch("/contacts/c9", json={"given_name": "x"}).status_code == 404

    def test_delete(self, client, contacts):
        contacts.delete.return_value = True
        assert client.delete("/contacts/c1").json() == {"id": "c1", "status": "deleted"}
