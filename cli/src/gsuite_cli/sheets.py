"""Sheets CLI commands."""

import csv
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_sheets import Sheets
from gsuite_sheets.spreadsheet import Spreadsheet
from gsuite_sheets.worksheet import Worksheet

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_sheets() -> "Sheets":
    """Get authenticated Sheets client."""
    from gsuite_core import GoogleAuth

    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print("[red]Not authenticated. Run: gsuite auth login[/red]")
            raise typer.Exit(1)

    return Sheets(auth)


@app.command("list")
def list_spreadsheets(
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """List all spreadsheets."""
    sheets = get_sheets()

    with console.status("[bold green]Fetching spreadsheets..."):
        spreadsheets = sheets.list_spreadsheets(max_results=limit)

    if output == "json":
        print_json(spreadsheets)
    else:
        if not spreadsheets:
            console.print("[yellow]No spreadsheets found[/yellow]")
            return

        table = Table(title=f"Spreadsheets ({len(spreadsheets)})")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="dim")

        for ss in spreadsheets:
            table.add_row(ss["name"], ss["id"][:40])

        console.print(table)


@app.command("open")
def open_spreadsheet(
    identifier: str = typer.Argument(..., help="Title, ID, or URL"),
) -> None:
    """Open and display spreadsheet info."""
    with console.status("[bold green]Opening spreadsheet..."):
        doc = _open(identifier)

    console.print(f"[bold]{doc.title}[/bold]")
    console.print(f"[dim]ID: {doc.id}[/dim]")
    console.print(f"[dim]URL: {doc.url}[/dim]")
    console.print()

    table = Table(title="Worksheets")
    table.add_column("Index", width=6)
    table.add_column("Title", style="cyan")
    table.add_column("Size")

    for ws in doc.worksheets:
        table.add_row(
            str(ws.index),
            ws.title,
            f"{ws.row_count} × {ws.column_count}",
        )

    console.print(table)


def _open(spreadsheet: str) -> Spreadsheet:
    """Open by URL, ID or title."""
    sheets_client = get_sheets()
    try:
        if spreadsheet.startswith("http"):
            return sheets_client.open_by_url(spreadsheet)
        if len(spreadsheet) > 30:  # Likely an ID
            return sheets_client.open_by_key(spreadsheet)
        return sheets_client.open(spreadsheet)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e


def _worksheet(doc: Spreadsheet, sheet: str | None) -> Worksheet:
    ws = doc.worksheet(sheet) if sheet else doc.sheet1
    if not ws:
        console.print(f"[red]Worksheet not found: {sheet}[/red]")
        raise typer.Exit(1)
    return ws


SPREADSHEET_ARG = typer.Argument(..., help="Spreadsheet title, ID or URL")
SHEET_OPT = typer.Option(None, "--sheet", "-s", help="Worksheet name (default: first)")
RAW_OPT = typer.Option(False, "--raw", help="Store values as-is instead of parsing formulas/dates")


@app.command("read")
def read_range(
    spreadsheet: str = SPREADSHEET_ARG,
    cell_range: str = typer.Option("A1:Z100", "--range", "-r", help="Range in A1 notation"),
    sheet: str | None = SHEET_OPT,
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json, csv"),
) -> None:
    """Read values from a spreadsheet range."""
    with console.status("[bold green]Reading data..."):
        ws = _worksheet(_open(spreadsheet), sheet)
        values = ws.get(cell_range)

    if not values:
        console.print("[yellow]No data found[/yellow]")
        return

    if output == "json":
        print_json(values)
    elif output == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerows(values)
    else:
        width = max(len(row) for row in values)
        table = Table(title=f"{ws.title}!{cell_range}")
        for i in range(width):
            table.add_column(Worksheet._col_to_letter(i + 1), style="cyan")
        for row in values:
            # The API trims trailing empty cells, so rows can be shorter
            table.add_row(*[str(cell) for cell in row], *[""] * (width - len(row)))
        console.print(table)


@app.command("write")
def write_cell(
    spreadsheet: str = SPREADSHEET_ARG,
    cell: str = typer.Option(..., "--cell", "-c", help="Cell reference (e.g., A1)"),
    value: str = typer.Option(..., "--value", "-v", help="Value to write"),
    sheet: str | None = SHEET_OPT,
    raw: bool = RAW_OPT,
) -> None:
    """Write a value to a cell."""
    with console.status("[bold green]Writing data..."):
        ws = _worksheet(_open(spreadsheet), sheet)
        ws.update(cell, [[value]], value_input="RAW" if raw else "USER_ENTERED")

    console.print(f"[green]✓ Written '{value}' to {ws.title}!{cell}[/green]")


@app.command("append")
def append_row(
    spreadsheet: str = SPREADSHEET_ARG,
    values: list[str] = typer.Option(..., "--value", "-v", help="Values (repeat for each column)"),
    sheet: str | None = SHEET_OPT,
    raw: bool = RAW_OPT,
) -> None:
    """Append a row to a spreadsheet."""
    with console.status("[bold green]Appending row..."):
        ws = _worksheet(_open(spreadsheet), sheet)
        ws.append_row(list(values), value_input="RAW" if raw else "USER_ENTERED")

    console.print(f"[green]✓ Appended row with {len(values)} values[/green]")


@app.command("replace")
def replace(
    spreadsheet: str = SPREADSHEET_ARG,
    find: str = typer.Argument(..., help="Text (or regex with --regex) to find"),
    replacement: str = typer.Argument(..., help="Replacement text"),
    sheet: str | None = typer.Option(
        None, "--sheet", "-s", help="Only this worksheet (default: all)"
    ),
    regex: bool = typer.Option(False, "--regex", help="Treat FIND as a regular expression"),
    match_case: bool = typer.Option(False, "--match-case", help="Case-sensitive"),
    whole_cell: bool = typer.Option(False, "--whole-cell", help="Only cells that match entirely"),
) -> None:
    """Find and replace text."""
    doc = _open(spreadsheet)
    sheet_id = _worksheet(doc, sheet).id if sheet else None
    assert doc._sheets is not None
    changed = doc._sheets.find_replace(
        doc.id,
        find,
        replacement,
        sheet_id=sheet_id,
        match_case=match_case,
        match_entire_cell=whole_cell,
        regex=regex,
    )
    console.print(f"[green]✓ Replaced {changed} occurrence(s)[/green]")


@app.command("freeze")
def freeze(
    spreadsheet: str = SPREADSHEET_ARG,
    rows: int | None = typer.Option(None, "--rows", min=0, help="Rows to freeze (0 unfreezes)"),
    cols: int | None = typer.Option(None, "--cols", min=0, help="Columns to freeze (0 unfreezes)"),
    sheet: str | None = SHEET_OPT,
) -> None:
    """Freeze header rows and/or columns."""
    if rows is None and cols is None:
        console.print("[red]Give --rows, --cols or both[/red]")
        raise typer.Exit(2)
    ws = _worksheet(_open(spreadsheet), sheet)
    ws.freeze(rows=rows, cols=cols)
    console.print(f"[green]✓ Frozen on {ws.title}[/green]")


@app.command("add-tab")
def add_tab(
    spreadsheet: str = SPREADSHEET_ARG,
    title: str = typer.Argument(..., help="New worksheet title"),
) -> None:
    """Add a worksheet."""
    ws = _open(spreadsheet).add_worksheet(title)
    console.print(f"[green]✓ Added worksheet {ws.title}[/green] [dim](id {ws.id})[/dim]")


@app.command("rename-tab")
def rename_tab(
    spreadsheet: str = SPREADSHEET_ARG,
    sheet: str = typer.Argument(..., help="Current worksheet name"),
    title: str = typer.Argument(..., help="New name"),
) -> None:
    """Rename a worksheet."""
    _worksheet(_open(spreadsheet), sheet).rename(title)
    console.print(f"[green]✓ Renamed {sheet} → {title}[/green]")


@app.command("delete-tab")
def delete_tab(
    spreadsheet: str = SPREADSHEET_ARG,
    sheet: str = typer.Argument(..., help="Worksheet name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
) -> None:
    """Delete a worksheet and its data."""
    doc = _open(spreadsheet)
    ws = _worksheet(doc, sheet)
    if not yes:
        typer.confirm(f"Delete worksheet {ws.title!r} and all its data?", abort=True)
    doc.del_worksheet(ws)
    console.print(f"[green]✓ Deleted worksheet {ws.title}[/green]")


@app.command("create")
def create_spreadsheet(
    title: str = typer.Argument(..., help="Spreadsheet title"),
) -> None:
    """Create a new spreadsheet."""
    sheets = get_sheets()

    with console.status("[bold green]Creating spreadsheet..."):
        doc = sheets.create(title)

    console.print(f"[green]✓ Created spreadsheet: {doc.title}[/green]")
    console.print(f"  ID: {doc.id}")
    console.print(f"  URL: {doc.url}")


@app.command("export")
def export(
    spreadsheet: str = SPREADSHEET_ARG,
    format: str = typer.Option("pdf", "--format", "-f", help="pdf, xlsx, ods, csv, tsv or html"),
    out: Path | None = typer.Option(
        None, "--out", help="File to write (default: <title>.<format>)"
    ),
) -> None:
    """Download a spreadsheet (csv/tsv: first sheet only)."""
    doc = _open(spreadsheet)
    with console.status("[bold green]Exporting..."):
        content = doc.export(format)
    path = out or Path(f"{doc.title}.{'zip' if format == 'html' else format}")
    path.write_bytes(content)
    console.print(f"[green]✓ Saved[/green] {path}")


@app.command("import-csv")
def import_csv(
    spreadsheet: str = SPREADSHEET_ARG,
    csv_file: Path = typer.Argument(..., exists=True, dir_okay=False, help="CSV file"),
    sheet: str | None = SHEET_OPT,
    append: bool = typer.Option(False, "--append", help="Keep existing data (default: replace)"),
    delimiter: str = typer.Option(",", "--delimiter", "-d", help="Field separator"),
) -> None:
    """Load a CSV into a worksheet, replacing its contents unless --append."""
    ws = _worksheet(_open(spreadsheet), sheet)
    with (
        csv_file.open(newline="", encoding="utf-8") as handle,
        console.status("[bold green]Importing..."),
    ):
        if append:
            rows = list(csv.reader(handle, delimiter=delimiter))
            ws.append_rows(rows, value_input="RAW")
        else:
            ws.import_csv(handle, delimiter=delimiter)
    console.print(f"[green]✓ Imported[/green] {csv_file} into {ws.title}")


@app.command("upsert")
def upsert(
    spreadsheet: str = SPREADSHEET_ARG,
    csv_file: Path = typer.Argument(..., exists=True, dir_okay=False, help="CSV with a header row"),
    key: str = typer.Option(..., "--key", "-k", help="Column that identifies a row"),
    sheet: str | None = SHEET_OPT,
) -> None:
    """Update rows matching on --key from a CSV, appending the new ones."""
    ws = _worksheet(_open(spreadsheet), sheet)
    with csv_file.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    result = ws.upsert(records, key=key)
    console.print(f"[green]✓ {result['updated']} updated, {result['appended']} appended[/green]")


@app.command("share")
def share(
    spreadsheet: str = SPREADSHEET_ARG,
    email: str = typer.Argument(..., help="Email to share with"),
    role: str = typer.Option("reader", "--role", "-r", help="reader, commenter or writer"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Email the user"),
) -> None:
    """Share a spreadsheet with someone."""
    doc = _open(spreadsheet)
    if not doc.share(email, role=role, notify=notify):
        console.print(f"[red]Spreadsheet not found: {spreadsheet}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Shared {doc.title} with {email} ({role})[/green]")
