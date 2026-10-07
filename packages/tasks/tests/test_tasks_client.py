"""Tasks client against a mocked Tasks API service."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from gsuite_core.exceptions import PermissionDeniedError, ValidationError
from gsuite_tasks import Task, Tasks
from gsuite_tasks.parser import format_due, parse_due, parse_timestamp

TASK = {
    "id": "t1",
    "title": "Pay rent",
    "notes": "Before the 5th",
    "status": "needsAction",
    "due": "2026-02-01T00:00:00.000Z",
    "updated": "2026-01-20T10:00:00.000Z",
    "position": "00000000000000000001",
    "webViewLink": "https://tasks.google.com/task/t1",
}


@pytest.fixture
def service():
    with patch("gsuite_tasks.client.build") as build:
        svc = MagicMock()
        build.return_value = svc
        yield svc


@pytest.fixture
def tasks(service):
    return Tasks(Mock())


class TestService:
    def test_lazy_build(self):
        auth = Mock()
        with patch("gsuite_tasks.client.build") as build:
            client = Tasks(auth)
            build.assert_not_called()
            assert client.service is build.return_value
        assert build.call_args.args == ("tasks", "v1")
        assert build.call_args.kwargs["http"].credentials is auth.credentials


class TestParsing:
    def test_parse_task(self, tasks, service):
        service.tasks().get().execute.return_value = TASK

        task = tasks.get_task("t1")

        assert task == Task(
            id="t1",
            title="Pay rent",
            tasklist_id="@default",
            notes="Before the 5th",
            due=date(2026, 2, 1),
            updated=datetime(2026, 1, 20, 10, tzinfo=UTC),
            position="00000000000000000001",
            web_view_link="https://tasks.google.com/task/t1",
            raw=TASK,
        )
        assert not task.is_completed
        assert not task.is_subtask

    def test_due_keeps_only_the_day(self):
        assert parse_due("2026-02-01T00:00:00.000Z") == date(2026, 2, 1)
        assert parse_due(None) is None
        assert parse_due("garbage") is None

    def test_format_due(self):
        assert format_due(date(2026, 2, 1)) == "2026-02-01T00:00:00.000Z"
        # A datetime is reduced to its day: the API drops the time anyway
        assert format_due(datetime(2026, 2, 1, 18, 30)) == "2026-02-01T00:00:00.000Z"

    def test_bad_timestamp(self):
        assert parse_timestamp("nope") is None
        assert parse_timestamp("") is None

    def test_overdue(self):
        yesterday = date.today() - timedelta(days=1)
        assert Task(id="1", title="x", tasklist_id="l", due=yesterday).is_overdue
        assert not Task(
            id="1", title="x", tasklist_id="l", due=yesterday, status="completed"
        ).is_overdue
        assert not Task(id="1", title="x", tasklist_id="l").is_overdue


class TestTaskLists:
    def test_list_follows_pages(self, tasks, service):
        service.tasklists().list().execute.side_effect = [
            {"items": [{"id": "a", "title": "Inbox"}], "nextPageToken": "p2"},
            {"items": [{"id": "b", "title": "Work", "updated": "2026-01-01T00:00:00Z"}]},
        ]

        lists = tasks.list_tasklists()

        assert [tl.title for tl in lists] == ["Inbox", "Work"]
        assert lists[1].updated == datetime(2026, 1, 1, tzinfo=UTC)
        assert service.tasklists().list.call_args.kwargs == {
            "maxResults": 100,
            "pageToken": "p2",
        }

    def test_get_missing(self, tasks, service, http_error):
        service.tasklists().get().execute.side_effect = http_error(404)
        assert tasks.get_tasklist("nope") is None

    def test_create_rename_delete(self, tasks, service):
        service.tasklists().insert().execute.return_value = {"id": "l1", "title": "Home"}
        service.tasklists().patch().execute.return_value = {"id": "l1", "title": "House"}

        assert tasks.create_tasklist("Home").id == "l1"
        service.tasklists().insert.assert_called_with(body={"title": "Home"})
        assert tasks.rename_tasklist("l1", "House").title == "House"
        service.tasklists().patch.assert_called_with(tasklist="l1", body={"title": "House"})
        assert tasks.delete_tasklist("l1") is True
        service.tasklists().delete.assert_called_with(tasklist="l1")

    def test_delete_missing(self, tasks, service, http_error):
        service.tasklists().delete().execute.side_effect = http_error(404)
        assert tasks.delete_tasklist("nope") is False


class TestListTasks:
    def test_defaults(self, tasks, service):
        service.tasks().list().execute.return_value = {"items": [TASK]}

        result = tasks.list_tasks()

        assert [t.id for t in result] == ["t1"]
        assert service.tasks().list.call_args.kwargs == {
            "tasklist": "@default",
            "showCompleted": True,
            "showHidden": False,
            "maxResults": 100,
        }

    def test_filters_and_list(self, tasks, service):
        service.tasks().list().execute.return_value = {"items": [TASK]}

        result = tasks.list_tasks(
            "work",
            show_completed=False,
            due_min=date(2026, 2, 1),
            due_max=date(2026, 2, 28),
            max_results=5,
        )

        assert result[0].tasklist_id == "work"
        params = service.tasks().list.call_args.kwargs
        assert params["tasklist"] == "work"
        assert params["showCompleted"] is False
        assert params["dueMin"] == "2026-02-01T00:00:00.000Z"
        # due is midnight UTC: the bound covers the whole last day
        assert params["dueMax"] == "2026-02-28T23:59:59.999Z"
        assert params["maxResults"] == 5

    def test_client_default_list(self, service):
        service.tasks().list().execute.return_value = {}
        Tasks(Mock(), tasklist_id="work").list_tasks()
        assert service.tasks().list.call_args.kwargs["tasklist"] == "work"


class TestWriteTasks:
    def test_create(self, tasks, service):
        service.tasks().insert().execute.return_value = TASK

        task = tasks.create_task("Pay rent", notes="Before the 5th", due=date(2026, 2, 1))

        assert task.id == "t1"
        service.tasks().insert.assert_called_with(
            tasklist="@default",
            body={
                "title": "Pay rent",
                "notes": "Before the 5th",
                "due": "2026-02-01T00:00:00.000Z",
            },
        )

    def test_create_subtask_after_sibling(self, tasks, service):
        service.tasks().insert().execute.return_value = {**TASK, "parent": "p"}

        task = tasks.create_task("Step", tasklist_id="l", parent="p", previous="s")

        assert task.is_subtask
        kwargs = service.tasks().insert.call_args.kwargs
        assert (kwargs["parent"], kwargs["previous"]) == ("p", "s")

    def test_create_requires_title(self, tasks):
        with pytest.raises(ValidationError):
            tasks.create_task("  ")

    def test_update_sends_only_given_fields(self, tasks, service):
        service.tasks().patch().execute.return_value = TASK

        tasks.update_task("t1", title="New")
        assert service.tasks().patch.call_args.kwargs["body"] == {"title": "New"}

        tasks.update_task("t1", notes=None, due=None)
        assert service.tasks().patch.call_args.kwargs["body"] == {"notes": None, "due": None}

        tasks.update_task("t1", due=date(2026, 3, 1))
        assert service.tasks().patch.call_args.kwargs["body"] == {"due": "2026-03-01T00:00:00.000Z"}

    def test_update_nothing(self, tasks):
        with pytest.raises(ValidationError):
            tasks.update_task("t1")

    def test_complete_and_reopen(self, tasks, service):
        service.tasks().patch().execute.return_value = {**TASK, "status": "completed"}

        assert tasks.complete_task("t1").is_completed
        assert service.tasks().patch.call_args.kwargs == {
            "tasklist": "@default",
            "task": "t1",
            "body": {"status": "completed"},
        }

        tasks.reopen_task("t1", tasklist_id="l")
        # Without clearing `completed` the API keeps the task done
        assert service.tasks().patch.call_args.kwargs["body"] == {
            "status": "needsAction",
            "completed": None,
        }

    def test_move(self, tasks, service):
        service.tasks().move().execute.return_value = TASK

        tasks.move_task("t1", parent="p")
        assert service.tasks().move.call_args.kwargs == {
            "tasklist": "@default",
            "task": "t1",
            "parent": "p",
        }

        tasks.move_task("t1", previous="s")
        assert "parent" not in service.tasks().move.call_args.kwargs  # back to top level

    def test_delete(self, tasks, service, http_error):
        assert tasks.delete_task("t1") is True
        service.tasks().delete().execute.side_effect = http_error(404)
        assert tasks.delete_task("t1") is False

    def test_delete_other_errors_raise(self, tasks, service, http_error):
        service.tasks().delete().execute.side_effect = http_error(403, "insufficientPermissions")
        with pytest.raises(PermissionDeniedError):
            tasks.delete_task("t1")

    def test_clear_completed(self, tasks, service):
        tasks.clear_completed("l")
        service.tasks().clear.assert_called_with(tasklist="l")
