"""Tasks, Contacts and `auth login --scopes` CLI commands with mocked clients."""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gsuite_cli.auth import _resolve_scopes
from gsuite_cli.main import app
from gsuite_contacts import Contact
from gsuite_core import Scopes
from gsuite_tasks import Task, TaskList

runner = CliRunner()


@pytest.fixture
def tasks():
    client = MagicMock()
    with patch("gsuite_cli.tasks.get_tasks", return_value=client):
        yield client


@pytest.fixture
def contacts():
    client = MagicMock()
    with patch("gsuite_cli.contacts.get_contacts", return_value=client):
        yield client


def _task(**overrides):
    fields = {"id": "t1", "title": "Pay rent", "tasklist_id": "@default"}
    fields.update(overrides)
    return Task(**fields)


class TestTasks:
    def test_lists(self, tasks):
        tasks.list_tasklists.return_value = [TaskList(id="l1", title="Inbox")]
        result = runner.invoke(app, ["tasks", "lists", "-o", "json"])
        assert json.loads(result.output) == [{"id": "l1", "title": "Inbox"}]

    def test_list_pending_by_default(self, tasks):
        overdue = date.today() - timedelta(days=2)
        tasks.list_tasks.return_value = [_task(due=overdue), _task(id="t2", parent="t1")]

        result = runner.invoke(app, ["tasks", "ls", "--due-before", "2026-12-31"])

        assert result.exit_code == 0, result.output
        assert overdue.isoformat() in result.output
        tasks.list_tasks.assert_called_once_with(
            "@default", show_completed=False, due_max=date(2026, 12, 31), max_results=100
        )

    def test_list_json_all(self, tasks):
        tasks.list_tasks.return_value = [_task(status="completed", due=date(2026, 2, 1))]

        result = runner.invoke(app, ["tasks", "list", "-a", "-L", "work", "-o", "json"])

        assert json.loads(result.output)[0]["due"] == "2026-02-01"
        assert tasks.list_tasks.call_args.kwargs["show_completed"] is True
        assert tasks.list_tasks.call_args.args == ("work",)

    def test_list_empty(self, tasks):
        tasks.list_tasks.return_value = []
        assert "No tasks" in runner.invoke(app, ["tasks", "ls"]).output

    def test_add(self, tasks):
        tasks.create_task.return_value = _task()

        result = runner.invoke(app, ["tasks", "add", "Pay rent", "--due", "2026-02-01"])

        assert "Created" in result.output
        tasks.create_task.assert_called_once_with(
            "Pay rent", notes=None, due=date(2026, 2, 1), tasklist_id="@default", parent=None
        )

    def test_bad_date(self, tasks):
        result = runner.invoke(app, ["tasks", "add", "x", "--due", "tomorrow"])
        assert result.exit_code != 0
        tasks.create_task.assert_not_called()

    def test_done_reopen_clear(self, tasks):
        tasks.complete_task.return_value = _task(status="completed")
        tasks.reopen_task.return_value = _task()

        assert "Completed" in runner.invoke(app, ["tasks", "done", "t1"]).output
        assert "Reopened" in runner.invoke(app, ["tasks", "reopen", "t1"]).output
        runner.invoke(app, ["tasks", "clear", "-L", "work"])
        tasks.clear_completed.assert_called_once_with("work")

    def test_rm_missing(self, tasks):
        tasks.delete_task.return_value = False
        assert runner.invoke(app, ["tasks", "rm", "t9"]).exit_code == 1


def _contact(**overrides):
    fields = {
        "resource_name": "people/c1",
        "display_name": "Ana Pérez",
        "emails": ["ana@example.com"],
        "phones": ["+54 11 5555-5555"],
        "organization": "Acme",
        "job_title": "CTO",
    }
    fields.update(overrides)
    return Contact(**fields)


class TestContacts:
    def test_list(self, contacts):
        contacts.list_contacts.return_value = [_contact()]

        result = runner.invoke(app, ["contacts", "ls"])

        assert "Ana Pérez" in result.output
        contacts.list_contacts.assert_called_once_with(
            max_results=100, sort_order="FIRST_NAME_ASCENDING"
        )

    def test_search_json(self, contacts):
        contacts.search.return_value = [_contact()]

        result = runner.invoke(app, ["contacts", "search", "ana", "-o", "json"])

        assert json.loads(result.output)[0]["id"] == "c1"
        contacts.search.assert_called_once_with("ana", max_results=10)

    def test_search_empty(self, contacts):
        contacts.search.return_value = []
        assert "No contacts" in runner.invoke(app, ["contacts", "search", "zz"]).output

    def test_show(self, contacts):
        contacts.get.return_value = _contact(notes="Met at PyCon")

        result = runner.invoke(app, ["contacts", "show", "c1"])

        assert "CTO · Acme" in result.output
        assert "ana@example.com" in result.output
        assert "Met at PyCon" in result.output

    def test_show_missing(self, contacts):
        contacts.get.return_value = None
        assert runner.invoke(app, ["contacts", "show", "c9"]).exit_code == 1

    def test_add_repeatable_options(self, contacts):
        contacts.create.return_value = _contact()

        result = runner.invoke(
            app, ["contacts", "add", "-g", "Ana", "-e", "a@x.com", "-e", "b@x.com"]
        )

        assert result.exit_code == 0, result.output
        kwargs = contacts.create.call_args.kwargs
        assert kwargs["emails"] == ["a@x.com", "b@x.com"]
        assert kwargs["phones"] is None

    def test_rm_asks_first(self, contacts):
        result = runner.invoke(app, ["contacts", "rm", "c1"], input="n\n")
        assert result.exit_code == 1
        contacts.delete.assert_not_called()

        contacts.delete.return_value = True
        assert "Deleted" in runner.invoke(app, ["contacts", "rm", "c1", "-y"]).output


class TestLoginScopes:
    def test_combined_sets_without_duplicates(self):
        scopes = _resolve_scopes("default, tasks,contacts")
        assert scopes[: len(Scopes.default())] == Scopes.default()
        assert Scopes.TASKS_FULL in scopes and Scopes.CONTACTS_FULL in scopes
        assert len(scopes) == len(set(scopes))

    def test_sheets_is_a_valid_set(self):
        assert _resolve_scopes("sheets") == Scopes.sheets()

    def test_unknown_set_is_an_error_not_the_default(self):
        result = runner.invoke(app, ["auth", "login", "--scopes", "calender"])
        assert result.exit_code == 1
        assert "Unknown scope set: calender" in result.output
