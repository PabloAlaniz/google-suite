"""Tag Manager CLI commands (read-only)."""

from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_core import GoogleAuth
from gsuite_tagmanager import TagManager

console = Console()
app = typer.Typer(no_args_is_help=True)

OUTPUT_OPTION = typer.Option("table", "--output", "-o", help="Output: table, json")
ACCOUNT_ARG = typer.Argument(..., help='Account path, e.g. "accounts/123"')
CONTAINER_ARG = typer.Argument(..., help='Container path, e.g. "accounts/123/containers/456"')
WORKSPACE_ARG = typer.Argument(
    ..., help='Workspace path, e.g. "accounts/1/containers/2/workspaces/3"'
)


def get_tagmanager() -> TagManager:
    """Get authenticated Tag Manager client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print(
                "[red]Not authenticated. Run: gsuite auth login --scopes default,tagmanager[/red]"
            )
            raise typer.Exit(1)

    return TagManager(auth)


def _show(
    items: list[dict[str, Any]],
    output: str,
    title: str,
    columns: list[tuple[str, Callable[[dict[str, Any]], Any]]],
) -> None:
    if output == "json":
        print_json(items)
        return

    if not items:
        console.print(f"[yellow]No {title.lower()}[/yellow]")
        return

    table = Table(title=f"{title} ({len(items)})")
    for i, (name, _) in enumerate(columns):
        table.add_column(name, style="cyan" if i == 0 else None)
    table.add_column("Path", style="dim")
    for item in items:
        table.add_row(*(str(get(item) or "") for _, get in columns), item.get("path", ""))
    console.print(table)


def _name(item: dict[str, Any]) -> Any:
    return item.get("name")


def _type(item: dict[str, Any]) -> Any:
    return item.get("type")


@app.command("accounts")
def accounts(output: str = OUTPUT_OPTION) -> None:
    """List Tag Manager accounts."""
    _show(get_tagmanager().list_accounts(), output, "Accounts", [("Name", _name)])


@app.command("containers")
def containers(account_path: str = ACCOUNT_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the containers of an account."""
    _show(
        get_tagmanager().list_containers(account_path),
        output,
        "Containers",
        [("Name", _name), ("Public ID", lambda c: c.get("publicId"))],
    )


@app.command("workspaces")
def workspaces(container_path: str = CONTAINER_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the workspaces of a container."""
    _show(get_tagmanager().list_workspaces(container_path), output, "Workspaces", [("Name", _name)])


@app.command("tags")
def tags(workspace_path: str = WORKSPACE_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the tags of a workspace."""
    _show(
        get_tagmanager().list_tags(workspace_path),
        output,
        "Tags",
        [("Name", _name), ("Type", _type)],
    )


@app.command("triggers")
def triggers(workspace_path: str = WORKSPACE_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the triggers of a workspace."""
    _show(
        get_tagmanager().list_triggers(workspace_path),
        output,
        "Triggers",
        [("Name", _name), ("Type", _type)],
    )


@app.command("variables")
def variables(workspace_path: str = WORKSPACE_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the variables of a workspace."""
    _show(
        get_tagmanager().list_variables(workspace_path),
        output,
        "Variables",
        [("Name", _name), ("Type", _type)],
    )


@app.command("versions")
def versions(container_path: str = CONTAINER_ARG, output: str = OUTPUT_OPTION) -> None:
    """List the versions of a container."""
    _show(
        get_tagmanager().list_versions(container_path),
        output,
        "Versions",
        [
            ("ID", lambda v: v.get("containerVersionId")),
            ("Name", _name),
            ("Tags", lambda v: v.get("numTags")),
        ],
    )
