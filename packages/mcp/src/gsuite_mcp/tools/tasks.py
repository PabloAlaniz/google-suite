"""Tasks tools: list, add and complete tasks."""

from __future__ import annotations

from typing import Any

from gsuite_mcp.serialize import to_json
from gsuite_mcp.services import Services
from gsuite_mcp.tools._common import (
    READ,
    WRITE,
    ToolDecorator,
    parse_day,
    results,
)


def register(tool: ToolDecorator, svc: Services) -> None:
    """Register the tasks tools on the server."""

    @tool(READ)
    def tasks_list(
        tasklist_id: str = "@default",
        show_completed: bool = False,
        due_before: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Tasks of a list (default: the user's main list), pending only unless
        show_completed. Needs the Tasks scope.
        """
        tasks = svc.tasks.list_tasks(
            tasklist_id,
            show_completed=show_completed,
            due_max=parse_day(due_before),
            max_results=max_results,
        )
        return results(to_json(tasks))

    @tool(WRITE)
    def tasks_add(
        title: str,
        notes: str | None = None,
        due: str | None = None,
        tasklist_id: str = "@default",
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task (a subtask when `parent` is a task ID). `due` is a day."""
        task = svc.tasks.create_task(
            title, notes=notes, due=parse_day(due), tasklist_id=tasklist_id, parent=parent
        )
        return to_json(task)  # type: ignore[no-any-return]

    @tool(WRITE)
    def tasks_complete(task_id: str, tasklist_id: str = "@default") -> dict[str, Any]:
        """Mark a task as completed."""
        return to_json(svc.tasks.complete_task(task_id, tasklist_id=tasklist_id))  # type: ignore[no-any-return]
