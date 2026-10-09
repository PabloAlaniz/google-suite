"""Drive CLI commands."""

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_core import GoogleAuth
from gsuite_drive import Drive, File

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_drive() -> Drive:
    """Get authenticated Drive client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print("[red]Not authenticated. Run: gsuite auth login[/red]")
            raise typer.Exit(1)

    return Drive(auth)


def _require(file: File | None, file_id: str) -> File:
    if file is None:
        console.print(f"[red]File not found: {file_id}[/red]")
        raise typer.Exit(1)
    return file


def _size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _as_dict(f: File) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "mime_type": f.mime_type,
        "size": f.size,
        "modified_time": f.modified_time.isoformat() if f.modified_time else None,
        "parents": f.parents,
        "web_view_link": f.web_view_link,
    }


@app.command("list")
@app.command("ls", hidden=True)
def list_files(
    parent: str | None = typer.Argument(None, help="Folder ID (default: everything)"),
    query: str | None = typer.Option(None, "--query", "-q", help="Raw Drive query"),
    name: str | None = typer.Option(None, "--name", "-n", help="Name contains"),
    trashed: bool = typer.Option(False, "--trashed", help="List the trash"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max files"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """List files."""
    drive = get_drive()

    if name:
        from gsuite_core import drive_query_literal

        name_query = f"name contains {drive_query_literal(name)}"
        query = f"({query}) and {name_query}" if query else name_query

    with console.status("[bold green]Listing files..."):
        files = drive.list_files(query=query, parent_id=parent, max_results=limit, trashed=trashed)

    if output == "json":
        print_json([_as_dict(f) for f in files])
        return

    if not files:
        console.print("[yellow]No files found[/yellow]")
        return

    table = Table(title=f"Files ({len(files)})")
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified", style="dim")
    table.add_column("ID", style="dim")
    for f in files:
        size = "—" if f.is_folder or f.is_google_doc else _size(f.size)
        name_cell = f"{f.name}/" if f.is_folder else f.name
        modified = f.modified_time.strftime("%Y-%m-%d %H:%M") if f.modified_time else ""
        table.add_row(name_cell, size, modified, f.id)
    console.print(table)


@app.command("info")
def info(
    file_id: str = typer.Argument(..., help="File ID"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """Show file metadata and who has access."""
    drive = get_drive()
    file = _require(drive.get(file_id), file_id)

    if output == "json":
        data = _as_dict(file)
        data["permissions"] = [vars(p) for p in drive.list_permissions(file_id)]
        print_json(data)
        return

    console.print(f"[bold]{file.name}[/bold]  [dim]{file.mime_type}[/dim]")
    console.print(f"[dim]ID: {file.id}[/dim]")
    if file.web_view_link:
        console.print(f"[dim]{file.web_view_link}[/dim]")
    for perm in drive.list_permissions(file_id):
        who = perm.email_address or perm.domain or perm.type
        console.print(f"  {perm.role:<10} {who}")


@app.command("upload")
def upload(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Local file"),
    parent: str | None = typer.Option(None, "--to", help="Destination folder ID"),
    name: str | None = typer.Option(None, "--name", help="Name in Drive"),
) -> None:
    """Upload a file (resumable; large files are sent in chunks)."""
    drive = get_drive()

    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Uploading {path.name}", total=1.0)
        file = drive.upload(
            str(path),
            name=name,
            parent_id=parent,
            on_progress=lambda done: progress.update(task, completed=done),
        )

    console.print(f"[green]✓ Uploaded[/green] {file.name} [dim]({file.id})[/dim]")


@app.command("download")
def download(
    file_id: str = typer.Argument(..., help="File ID"),
    dest: Path | None = typer.Option(None, "--out", help="Local path (default: Drive name)"),
    export: str | None = typer.Option(
        None, "--export", "-e", help="Export format for Google files: pdf, docx, xlsx, csv, ..."
    ),
) -> None:
    """Download a file. Google Docs/Sheets/Slides are exported."""
    drive = get_drive()
    file = _require(drive.get(file_id), file_id)

    with console.status(f"[bold green]Downloading {file.name}..."):
        path = file.download(str(dest) if dest else None, export_format=export)

    console.print(f"[green]✓ Saved[/green] {path}")


@app.command("mkdir")
def mkdir(
    name: str = typer.Argument(..., help="Folder name"),
    parent: str | None = typer.Option(None, "--in", help="Parent folder ID"),
) -> None:
    """Create a folder."""
    folder = get_drive().create_folder(name, parent_id=parent)
    console.print(f"[green]✓ Created[/green] {folder.name}/ [dim]({folder.id})[/dim]")


@app.command("move")
@app.command("mv", hidden=True)
def move(
    file_id: str = typer.Argument(..., help="File ID"),
    parent: str = typer.Argument(..., help="Destination folder ID"),
) -> None:
    """Move a file to another folder."""
    file = get_drive().move(file_id, parent)
    console.print(f"[green]✓ Moved[/green] {file.name}")


@app.command("delete")
@app.command("rm", hidden=True)
def remove(
    file_id: str = typer.Argument(..., help="File ID"),
    permanent: bool = typer.Option(False, "--permanent", help="Delete forever instead of trashing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
) -> None:
    """Move a file to the trash (or delete it permanently)."""
    drive = get_drive()

    if permanent:
        if not yes:
            typer.confirm(f"Permanently delete {file_id}? This can't be undone", abort=True)
        found = drive.delete(file_id)
    else:
        found = drive.trash(file_id)

    if not found:
        console.print(f"[red]File not found: {file_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ {'Deleted' if permanent else 'Trashed'}[/green] {file_id}")


@app.command("share")
def share(
    file_id: str = typer.Argument(..., help="File ID"),
    email: str | None = typer.Argument(None, help="User email (omit with --anyone)"),
    role: str = typer.Option("reader", "--role", "-r", help="reader, commenter or writer"),
    anyone: bool = typer.Option(False, "--anyone", help="Anyone with the link"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Email the user"),
) -> None:
    """Share a file with a user, or with anyone who has the link."""
    if not email and not anyone:
        console.print("[red]Give an email or --anyone[/red]")
        raise typer.Exit(2)

    perm = get_drive().add_permission(
        file_id,
        role=role,
        type="anyone" if anyone else "user",
        email=email,
        notify=notify,
    )
    console.print(
        f"[green]✓ Shared[/green] as {perm.role} with {perm.email_address or 'anyone with the link'}"
    )
