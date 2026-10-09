"""Google Suite Tasks - Simple Tasks API client."""

__version__ = "0.1.0"

from gsuite_tasks.client import Tasks
from gsuite_tasks.task import Task, TaskList

__all__ = [
    "Tasks",
    "Task",
    "TaskList",
]
