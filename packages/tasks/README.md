# gsuite-tasks

Simple, Pythonic Google Tasks API client.

## Installation

```bash
pip install gsuite-sdk   # gsuite_tasks ships inside the SDK
```

Enable the **Google Tasks API** in your Cloud project and log in with the Tasks
scope (it is not in the default login):

```bash
gsuite auth login --force --scopes default,tasks
```

## Quick Start

```python
from datetime import date

from gsuite_core import GoogleAuth, Scopes
from gsuite_tasks import Tasks

auth = GoogleAuth(scopes=Scopes.default() + Scopes.tasks())
auth.authenticate()

tasks = Tasks(auth)  # the user's default list ("@default")

for tl in tasks.list_tasklists():
    print(tl.id, tl.title)

task = tasks.create_task("Pay rent", due=date(2026, 2, 1), notes="Before the 5th")
tasks.create_task("Transfer", parent=task.id)        # subtask
for t in tasks.list_tasks(show_completed=False, due_max=date(2026, 2, 28)):
    print(t.title, t.due, "overdue" if t.is_overdue else "")

tasks.complete_task(task.id)
tasks.reopen_task(task.id)
tasks.update_task(task.id, due=None)                 # None clears a field
tasks.move_task(task.id, previous="other-task-id")
tasks.clear_completed()                              # hide completed tasks
```

`due` is a `date`: the Tasks API stores only the day and discards any time.
`get_task` / `get_tasklist` return `None` and the `delete_*` methods return
`False` when the resource doesn't exist; other errors raise `GSuiteError`
subclasses.
