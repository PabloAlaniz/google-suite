"""Convert Tasks API resources to entities and back."""

from datetime import date, datetime
from typing import Any

from gsuite_tasks.task import Task, TaskList


def parse_timestamp(value: str | None) -> datetime | None:
    """RFC 3339 timestamp ("2026-01-01T10:00:00.000Z") to an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_due(value: str | None) -> date | None:
    """The API sends due as a midnight-UTC timestamp; only the day is meaningful."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def format_due(value: date) -> str:
    """A date as the timestamp the API expects for ``due``."""
    if isinstance(value, datetime):
        value = value.date()  # the API discards the time anyway
    return f"{value.isoformat()}T00:00:00.000Z"


class TasksParser:
    """Parses Tasks API resources."""

    @staticmethod
    def parse_tasklist(data: dict[str, Any]) -> TaskList:
        return TaskList(
            id=data["id"],
            title=data.get("title", ""),
            updated=parse_timestamp(data.get("updated")),
            raw=data,
        )

    @staticmethod
    def parse_task(data: dict[str, Any], tasklist_id: str) -> Task:
        return Task(
            id=data["id"],
            title=data.get("title", ""),
            tasklist_id=tasklist_id,
            notes=data.get("notes"),
            status=data.get("status", "needsAction"),
            due=parse_due(data.get("due")),
            completed=parse_timestamp(data.get("completed")),
            updated=parse_timestamp(data.get("updated")),
            parent=data.get("parent"),
            position=data.get("position"),
            deleted=data.get("deleted", False),
            hidden=data.get("hidden", False),
            web_view_link=data.get("webViewLink"),
            raw=data,
        )
