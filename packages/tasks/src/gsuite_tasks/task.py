"""Task and TaskList entities."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class TaskList:
    """A Google Tasks list."""

    id: str
    title: str
    updated: datetime | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Task:
    """A task in a task list.

    ``due`` is a date: the Tasks API stores only the day and discards any time.
    """

    id: str
    title: str
    tasklist_id: str
    notes: str | None = None
    status: str = "needsAction"
    due: date | None = None
    completed: datetime | None = None
    updated: datetime | None = None
    parent: str | None = None
    position: str | None = None
    deleted: bool = False
    hidden: bool = False
    web_view_link: str | None = None

    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @property
    def is_subtask(self) -> bool:
        return self.parent is not None

    @property
    def is_overdue(self) -> bool:
        """Open and due before today (in local time)."""
        return not self.is_completed and self.due is not None and self.due < date.today()
