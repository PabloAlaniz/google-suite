"""Tasks CLI commands."""

from datetime import date

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_core import GoogleAuth
from gsuite_tasks import Task, Tasks

console = Console()
app = typer.Typer(no_args_is_help=True)

LIST_OPTION = typer.Option("@default", "--list", "-L", help="Task list ID (default list)")


def get_tasks() -> Tasks:
    """Get authenticated Tasks client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print(
                "[red]Not authenticated. Run: gsuite auth login --scopes default,tasks[/red]"
            )
            raise typer.Exit(1)

    return Tasks(auth)


def _day(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"{value!r} is not a YYYY-MM-DD date") from None


def _as_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "tasklist_id": t.tasklist_id,
        "status": t.status,
        "due": t.due.isoformat() if t.due else None,
        "notes": t.notes,
        "parent": t.parent,
        "completed": t.completed.isoformat() if t.completed else None,
    }


@app.command("lists")
def lists(
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """List task lists."""
    tasklists = get_tasks().list_tasklists()

    if output == "json":
        print_json([{"id": tl.id, "title": tl.title} for tl in tasklists])
        return

    table = Table(title=f"Task lists ({len(tasklists)})")
    table.add_column("Title", style="cyan")
    table.add_column("ID", style="dim")
    for tl in tasklists:
        table.add_row(tl.title, tl.id)
    console.print(table)


@app.command("list")
@app.command("ls", hidden=True)
def list_tasks(
    tasklist: str = LIST_OPTION,
    show_all: bool = typer.Option(False, "--all", "-a", help="Include completed tasks"),
    due_before: str | None = typer.Option(None, "--due-before", help="Due on or before YYYY-MM-DD"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max tasks"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """List tasks (pending only, unless --all)."""
    result = get_tasks().list_tasks(
        tasklist, show_completed=show_all, due_max=_day(due_before), max_results=limit
    )

    if output == "json":
        print_json([_as_dict(t) for t in result])
        return

    if not result:
        console.print("[yellow]No tasks[/yellow]")
        return

    table = Table(title=f"Tasks ({len(result)})")
    table.add_column("", width=1)
    table.add_column("Title", style="cyan")
    table.add_column("Due")
    table.add_column("ID", style="dim")
    for t in result:
        due = t.due.isoformat() if t.due else ""
        if t.is_overdue:
            due = f"[red]{due}[/red]"
        title = f"  {t.title}" if t.is_subtask else t.title
        table.add_row("✓" if t.is_completed else "", title, due, t.id)
    console.print(table)


@app.command("add")
def add(
    title: str = typer.Argument(..., help="Task title"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Notes"),
    due: str | None = typer.Option(None, "--due", "-d", help="Due date (YYYY-MM-DD)"),
    parent: str | None = typer.Option(None, "--parent", help="Parent task ID (subtask)"),
    tasklist: str = LIST_OPTION,
) -> None:
    """Create a task."""
    task = get_tasks().create_task(
        title, notes=notes, due=_day(due), tasklist_id=tasklist, parent=parent
    )
    console.print(f"[green]✓ Created[/green] {task.title} [dim]{task.id}[/dim]")


@app.command("done")
def done(
    task_id: str = typer.Argument(..., help="Task ID"),
    tasklist: str = LIST_OPTION,
) -> None:
    """Mark a task as completed."""
    task = get_tasks().complete_task(task_id, tasklist_id=tasklist)
    console.print(f"[green]✓ Completed[/green] {task.title}")


@app.command("reopen")
def reopen(
    task_id: str = typer.Argument(..., help="Task ID"),
    tasklist: str = LIST_OPTION,
) -> None:
    """Mark a completed task as pending again."""
    task = get_tasks().reopen_task(task_id, tasklist_id=tasklist)
    console.print(f"[green]✓ Reopened[/green] {task.title}")


@app.command("delete")
@app.command("rm", hidden=True)
def remove(
    task_id: str = typer.Argument(..., help="Task ID"),
    tasklist: str = LIST_OPTION,
) -> None:
    """Delete a task."""
    if not get_tasks().delete_task(task_id, tasklist_id=tasklist):
        console.print(f"[red]Task not found: {task_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Deleted[/green] {task_id}")


@app.command("clear")
def clear(tasklist: str = LIST_OPTION) -> None:
    """Hide the completed tasks of a list."""
    get_tasks().clear_completed(tasklist)
    console.print(f"[green]✓ Cleared completed tasks[/green] {tasklist}")
