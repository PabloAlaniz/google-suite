"""Tasks API routes."""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gsuite_api.dependencies import TasksDep
from gsuite_tasks import Task, TaskList

router = APIRouter()

DEFAULT_LIST_HELP = 'Task list ID; "@default" is the user\'s default list'


# ========== Models ==========


class TaskListResponse(BaseModel):
    id: str
    title: str
    updated: str | None


class TaskResponse(BaseModel):
    id: str
    title: str
    tasklist_id: str
    notes: str | None
    status: str
    completed: bool
    due: date | None
    completed_at: str | None
    updated: str | None
    parent: str | None
    position: str | None
    web_view_link: str | None


class TaskListRequest(BaseModel):
    title: str = Field(min_length=1)


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1)
    notes: str | None = None
    due: date | None = Field(None, description="Due day (the API ignores any time)")
    parent: str | None = Field(None, description="Create it as a subtask of this task")
    previous: str | None = Field(None, description="Place it after this sibling")


class UpdateTaskRequest(BaseModel):
    """Only the fields sent are changed; notes/due sent as null are cleared."""

    title: str | None = Field(None, min_length=1)
    notes: str | None = None
    due: date | None = None
    completed: bool | None = Field(None, description="true completes it, false reopens it")


class MoveTaskRequest(BaseModel):
    parent: str | None = Field(None, description="New parent (omit for top level)")
    previous: str | None = Field(None, description="Place it after this sibling (omit: first)")


def _tasklist(tl: TaskList) -> TaskListResponse:
    return TaskListResponse(
        id=tl.id, title=tl.title, updated=tl.updated.isoformat() if tl.updated else None
    )


def _task(t: Task) -> TaskResponse:
    return TaskResponse(
        id=t.id,
        title=t.title,
        tasklist_id=t.tasklist_id,
        notes=t.notes,
        status=t.status,
        completed=t.is_completed,
        due=t.due,
        completed_at=t.completed.isoformat() if t.completed else None,
        updated=t.updated.isoformat() if t.updated else None,
        parent=t.parent,
        position=t.position,
        web_view_link=t.web_view_link,
    )


# ========== Task lists ==========


@router.get("/lists")
def list_tasklists(tasks: TasksDep) -> dict[str, Any]:
    """All task lists."""
    lists = tasks.list_tasklists()
    return {"tasklists": [_tasklist(tl) for tl in lists], "count": len(lists)}


@router.post("/lists", status_code=201)
def create_tasklist(request: TaskListRequest, tasks: TasksDep) -> TaskListResponse:
    """Create a task list."""
    return _tasklist(tasks.create_tasklist(request.title))


@router.post("/lists/{list_id}:clear")
def clear_completed(list_id: str, tasks: TasksDep) -> dict[str, Any]:
    """Hide the completed tasks of a list."""
    tasks.clear_completed(list_id)
    return {"id": list_id, "status": "cleared"}


@router.get("/lists/{list_id}")
def get_tasklist(list_id: str, tasks: TasksDep) -> TaskListResponse:
    """A task list."""
    tasklist = tasks.get_tasklist(list_id)
    if tasklist is None:
        raise HTTPException(status_code=404, detail="Task list not found")
    return _tasklist(tasklist)


@router.patch("/lists/{list_id}")
def rename_tasklist(list_id: str, request: TaskListRequest, tasks: TasksDep) -> TaskListResponse:
    """Rename a task list."""
    return _tasklist(tasks.rename_tasklist(list_id, request.title))


@router.delete("/lists/{list_id}")
def delete_tasklist(list_id: str, tasks: TasksDep) -> dict[str, Any]:
    """Delete a task list and its tasks."""
    if not tasks.delete_tasklist(list_id):
        raise HTTPException(status_code=404, detail="Task list not found")
    return {"id": list_id, "status": "deleted"}


# ========== Tasks ==========


@router.get("/lists/{list_id}/tasks")
def list_tasks(
    list_id: str,
    tasks: TasksDep,
    show_completed: bool = True,
    show_hidden: bool = False,
    due_min: date | None = Query(None, description="Due on or after this day"),
    due_max: date | None = Query(None, description="Due on or before this day"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    """Tasks of a list."""
    result = tasks.list_tasks(
        list_id,
        show_completed=show_completed,
        show_hidden=show_hidden,
        due_min=due_min,
        due_max=due_max,
        max_results=limit,
    )
    return {"tasks": [_task(t) for t in result], "count": len(result)}


@router.post("/lists/{list_id}/tasks", status_code=201)
def create_task(list_id: str, request: CreateTaskRequest, tasks: TasksDep) -> TaskResponse:
    """Create a task."""
    task = tasks.create_task(
        request.title,
        notes=request.notes,
        due=request.due,
        tasklist_id=list_id,
        parent=request.parent,
        previous=request.previous,
    )
    return _task(task)


@router.post("/lists/{list_id}/tasks/{task_id}:move")
def move_task(
    list_id: str, task_id: str, request: MoveTaskRequest, tasks: TasksDep
) -> TaskResponse:
    """Move a task under another parent or after a sibling."""
    task = tasks.move_task(
        task_id, tasklist_id=list_id, parent=request.parent, previous=request.previous
    )
    return _task(task)


@router.get("/lists/{list_id}/tasks/{task_id}")
def get_task(list_id: str, task_id: str, tasks: TasksDep) -> TaskResponse:
    """A task."""
    task = tasks.get_task(task_id, tasklist_id=list_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task(task)


@router.patch("/lists/{list_id}/tasks/{task_id}")
def update_task(
    list_id: str, task_id: str, request: UpdateTaskRequest, tasks: TasksDep
) -> TaskResponse:
    """Change a task; only the fields you send are updated."""
    sent = request.model_fields_set
    changes: dict[str, Any] = {f: getattr(request, f) for f in ("notes", "due") if f in sent}
    if request.title is not None:
        changes["title"] = request.title
    if not changes and request.completed is None:
        raise HTTPException(status_code=422, detail="Nothing to update")

    task: Task | None = None
    if changes:
        task = tasks.update_task(task_id, tasklist_id=list_id, **changes)
    if request.completed is True:
        task = tasks.complete_task(task_id, tasklist_id=list_id)
    elif request.completed is False:
        task = tasks.reopen_task(task_id, tasklist_id=list_id)
    assert task is not None
    return _task(task)


@router.delete("/lists/{list_id}/tasks/{task_id}")
def delete_task(list_id: str, task_id: str, tasks: TasksDep) -> dict[str, Any]:
    """Delete a task."""
    if not tasks.delete_task(task_id, tasklist_id=list_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task_id, "status": "deleted"}
