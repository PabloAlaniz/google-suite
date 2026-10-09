"""Tasks client - high-level interface."""

import logging
from collections.abc import Iterator
from datetime import date
from typing import Any

from googleapiclient.discovery import build

from gsuite_core import GoogleAuth, authorized_http, execute, paginate
from gsuite_core.exceptions import NotFoundError, ValidationError
from gsuite_tasks.parser import TasksParser, format_due
from gsuite_tasks.task import Task, TaskList

logger = logging.getLogger(__name__)

DEFAULT_LIST = "@default"
MAX_PAGE_SIZE = 100  # tasklists.list and tasks.list both cap maxResults at 100

_UNSET: Any = object()


class Tasks:
    """
    High-level Google Tasks client.

    Example:
        auth = GoogleAuth(scopes=Scopes.tasks())
        auth.authenticate()

        tasks = Tasks(auth)

        for task in tasks.list_tasks():
            print(task.title, task.due)

        task = tasks.create_task("Pay rent", due=date(2026, 2, 1))
        tasks.complete_task(task.id)

    Task methods take an optional ``tasklist_id``; it defaults to the user's
    default list (``@default``).
    """

    def __init__(self, auth: GoogleAuth, tasklist_id: str = DEFAULT_LIST):
        self.auth = auth
        self.tasklist_id = tasklist_id
        self._service = None

    @property
    def service(self) -> Any:
        """Lazy-load Tasks API service."""
        if self._service is None:
            self._service = build(
                "tasks", "v1", http=authorized_http(self.auth.credentials), cache_discovery=False
            )
        return self._service

    def _list(self, tasklist_id: str | None) -> str:
        return tasklist_id or self.tasklist_id

    # ========== Task lists ==========

    def list_tasklists(self, max_results: int | None = None) -> list[TaskList]:
        """All task lists of the user."""
        items = paginate(
            self.service.tasklists().list,
            "items",
            "tasks",
            max_items=max_results,
            max_page_size=MAX_PAGE_SIZE,
        )
        return [TasksParser.parse_tasklist(item) for item in items]

    def get_tasklist(self, tasklist_id: str) -> TaskList | None:
        """A task list by ID, or None if it doesn't exist."""
        try:
            data = execute(
                self.service.tasklists().get(tasklist=tasklist_id),
                "tasks",
                "tasklist",
                tasklist_id,
            )
        except NotFoundError:
            return None
        return TasksParser.parse_tasklist(data)

    def create_tasklist(self, title: str) -> TaskList:
        """Create a task list."""
        data = execute(
            self.service.tasklists().insert(body={"title": title}), "tasks", "tasklist", title
        )
        return TasksParser.parse_tasklist(data)

    def rename_tasklist(self, tasklist_id: str, title: str) -> TaskList:
        """Change the title of a task list."""
        data = execute(
            self.service.tasklists().patch(tasklist=tasklist_id, body={"title": title}),
            "tasks",
            "tasklist",
            tasklist_id,
        )
        return TasksParser.parse_tasklist(data)

    def delete_tasklist(self, tasklist_id: str) -> bool:
        """Delete a task list and its tasks. False if it didn't exist."""
        try:
            execute(
                self.service.tasklists().delete(tasklist=tasklist_id),
                "tasks",
                "tasklist",
                tasklist_id,
            )
        except NotFoundError:
            return False
        return True

    # ========== Tasks ==========

    def iter_tasks(
        self,
        tasklist_id: str | None = None,
        show_completed: bool = True,
        show_hidden: bool = False,
        due_min: date | None = None,
        due_max: date | None = None,
        max_results: int | None = None,
    ) -> Iterator[Task]:
        """Iterate over the tasks of a list, following pagination.

        Args:
            show_completed: Include completed tasks.
            show_hidden: Include hidden tasks (completed and then cleared).
            due_min: Only tasks due on or after this day.
            due_max: Only tasks due on or before this day.
        """
        list_id = self._list(tasklist_id)
        params: dict[str, Any] = {
            "tasklist": list_id,
            "showCompleted": show_completed,
            "showHidden": show_hidden,
        }
        if due_min is not None:
            params["dueMin"] = format_due(due_min)
        if due_max is not None:
            # due is stored as midnight UTC; ending the bound at the end of the
            # day keeps that day in whether the API treats dueMax as inclusive or not.
            params["dueMax"] = f"{due_max.isoformat()}T23:59:59.999Z"
        for item in paginate(
            self.service.tasks().list,
            "items",
            "tasks",
            max_items=max_results,
            max_page_size=MAX_PAGE_SIZE,
            **params,
        ):
            yield TasksParser.parse_task(item, list_id)

    def list_tasks(self, tasklist_id: str | None = None, **kwargs: Any) -> list[Task]:
        """Tasks of a list (see ``iter_tasks`` for the filters)."""
        return list(self.iter_tasks(tasklist_id, **kwargs))

    def get_task(self, task_id: str, tasklist_id: str | None = None) -> Task | None:
        """A task by ID, or None if it doesn't exist."""
        list_id = self._list(tasklist_id)
        try:
            data = execute(
                self.service.tasks().get(tasklist=list_id, task=task_id), "tasks", "task", task_id
            )
        except NotFoundError:
            return None
        return TasksParser.parse_task(data, list_id)

    def create_task(
        self,
        title: str,
        notes: str | None = None,
        due: date | None = None,
        tasklist_id: str | None = None,
        parent: str | None = None,
        previous: str | None = None,
    ) -> Task:
        """Create a task.

        Args:
            due: Due day (the API ignores any time of day).
            parent: Create it as a subtask of this task.
            previous: Place it after this sibling (default: first position).
        """
        if not title.strip():
            raise ValidationError("title", "Task title cannot be empty")
        list_id = self._list(tasklist_id)
        body: dict[str, Any] = {"title": title}
        if notes is not None:
            body["notes"] = notes
        if due is not None:
            body["due"] = format_due(due)
        params: dict[str, Any] = {"tasklist": list_id, "body": body}
        if parent:
            params["parent"] = parent
        if previous:
            params["previous"] = previous
        data = execute(self.service.tasks().insert(**params), "tasks", "task", title)
        return TasksParser.parse_task(data, list_id)

    def update_task(
        self,
        task_id: str,
        tasklist_id: str | None = None,
        title: str | None = None,
        notes: str | None = _UNSET,
        due: date | None = _UNSET,
    ) -> Task:
        """Change fields of a task; only the given ones are sent.

        ``notes=None`` / ``due=None`` clear the field (omit them to leave it).
        """
        list_id = self._list(tasklist_id)
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if notes is not _UNSET:
            body["notes"] = notes
        if due is not _UNSET:
            body["due"] = format_due(due) if due is not None else None
        if not body:
            raise ValidationError("task", "Nothing to update")
        return self._patch(task_id, list_id, body)

    def complete_task(self, task_id: str, tasklist_id: str | None = None) -> Task:
        """Mark a task as completed."""
        return self._patch(task_id, self._list(tasklist_id), {"status": "completed"})

    def reopen_task(self, task_id: str, tasklist_id: str | None = None) -> Task:
        """Mark a completed task as pending again.

        ``completed`` must be cleared too, or the API keeps the task done.
        """
        return self._patch(
            task_id, self._list(tasklist_id), {"status": "needsAction", "completed": None}
        )

    def move_task(
        self,
        task_id: str,
        tasklist_id: str | None = None,
        parent: str | None = None,
        previous: str | None = None,
    ) -> Task:
        """Move a task: under ``parent`` (None = top level), after ``previous`` (None = first)."""
        list_id = self._list(tasklist_id)
        params: dict[str, Any] = {"tasklist": list_id, "task": task_id}
        if parent:
            params["parent"] = parent
        if previous:
            params["previous"] = previous
        data = execute(self.service.tasks().move(**params), "tasks", "task", task_id)
        return TasksParser.parse_task(data, list_id)

    def delete_task(self, task_id: str, tasklist_id: str | None = None) -> bool:
        """Delete a task. False if it didn't exist."""
        try:
            execute(
                self.service.tasks().delete(tasklist=self._list(tasklist_id), task=task_id),
                "tasks",
                "task",
                task_id,
            )
        except NotFoundError:
            return False
        return True

    def clear_completed(self, tasklist_id: str | None = None) -> None:
        """Hide the completed tasks of a list (they stay readable with show_hidden)."""
        list_id = self._list(tasklist_id)
        execute(self.service.tasks().clear(tasklist=list_id), "tasks", "tasklist", list_id)

    def _patch(self, task_id: str, tasklist_id: str, body: dict[str, Any]) -> Task:
        data = execute(
            self.service.tasks().patch(tasklist=tasklist_id, task=task_id, body=body),
            "tasks",
            "task",
            task_id,
        )
        return TasksParser.parse_task(data, tasklist_id)
