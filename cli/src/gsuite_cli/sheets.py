"""Sheets CLI commands."""

import json

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_sheets():
    """Get authenticated Sheets client."""
    from gsuite_core import GoogleAuth
    from gsuite_sheets import Sheets

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
):
    """List all spreadsheets."""
    sheets = get_sheets()

    with console.status("[bold green]Fetching spreadsheets..."):
        spreadsheets = sheets.list_spreadsheets(max_results=limit)

    if output == "json":
        console.print(json.dumps(spreadsheets, indent=2))
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
):
    """Open and display spreadsheet info."""
    sheets = get_sheets()

    with console.status("[bold green]Opening spreadsheet..."):
        try:
            if identifier.startswith("http"):
                doc = sheets.open_by_url(identifier)
            elif len(identifier) > 30:  # Likely an ID
                doc = sheets.open_by_key(identifier)
            else:
                doc = sheets.open(identifier)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

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


@app.command("read")
def read_range(
    spreadsheet: str = typer.Argument(..., help="Spreadsheet title or ID"),
    range: str = typer.Option("A1:Z100", "--range", "-r", help="Range in A1 notation"),
    sheet: str | None = typer.Option(None, "--sheet", "-s", help="Worksheet name"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json, csv"),
):
    """Read values from a spreadsheet range."""
    sheets_client = get_sheets()

    with console.status("[bold green]Reading data..."):
        try:
            if len(spreadsheet) > 30:
                doc = sheets_client.open_by_key(spreadsheet)
            else:
                doc = sheets_client.open(spreadsheet)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

        ws = doc.worksheet(sheet) if sheet else doc.sheet1
        if not ws:
            console.print(f"[red]Worksheet not found: {sheet}[/red]")
            raise typer.Exit(1)

        values = ws.get(range)

    if not values:
        console.print("[yellow]No data found[/yellow]")
        return

    if output == "json":
        console.print(json.dumps(values, indent=2))
    elif output == "csv":
        import csv
        import sys

        writer = csv.writer(sys.stdout)
        for row in values:
            writer.writerow(row)
    else:
        table = Table(title=f"{ws.title}!{range}")

        # Add columns
        if values:
            for i in range(len(values[0])):
                table.add_column(Worksheet._col_to_letter(i + 1), style="cyan")

        for row in values:
            table.add_row(*[str(cell) for cell in row])

        console.print(table)


@app.command("write")
def write_cell(
    spreadsheet: str = typer.Argument(..., help="Spreadsheet title or ID"),
    cell: str = typer.Option(..., "--cell", "-c", help="Cell reference (e.g., A1)"),
    value: str = typer.Option(..., "--value", "-v", help="Value to write"),
    sheet: str | None = typer.Option(None, "--sheet", "-s", help="Worksheet name"),
):
    """Write a value to a cell."""
    sheets_client = get_sheets()

    with console.status("[bold green]Writing data..."):
        try:
            if len(spreadsheet) > 30:
                doc = sheets_client.open_by_key(spreadsheet)
            else:
                doc = sheets_client.open(spreadsheet)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

        ws = doc.worksheet(sheet) if sheet else doc.sheet1
        if not ws:
            console.print(f"[red]Worksheet not found: {sheet}[/red]")
            raise typer.Exit(1)

        ws.update(cell, [[value]])

    console.print(f"[green]✓ Written '{value}' to {ws.title}!{cell}[/green]")


@app.command("append")
def append_row(
    spreadsheet: str = typer.Argument(..., help="Spreadsheet title or ID"),
    values: list[str] = typer.Option(..., "--value", "-v", help="Values (repeat for each column)"),
    sheet: str | None = typer.Option(None, "--sheet", "-s", help="Worksheet name"),
):
    """Append a row to a spreadsheet."""
    sheets_client = get_sheets()

    with console.status("[bold green]Appending row..."):
        try:
            if len(spreadsheet) > 30:
                doc = sheets_client.open_by_key(spreadsheet)
            else:
                doc = sheets_client.open(spreadsheet)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)

        ws = doc.worksheet(sheet) if sheet else doc.sheet1
        if not ws:
            console.print(f"[red]Worksheet not found: {sheet}[/red]")
            raise typer.Exit(1)

        ws.append_row(list(values))

    console.print(f"[green]✓ Appended row with {len(values)} values[/green]")


@app.command("create")
def create_spreadsheet(
    title: str = typer.Argument(..., help="Spreadsheet title"),
):
    """Create a new spreadsheet."""
    sheets = get_sheets()

    with console.status("[bold green]Creating spreadsheet..."):
        doc = sheets.create(title)

    console.print(f"[green]✓ Created spreadsheet: {doc.title}[/green]")
    console.print(f"  ID: {doc.id}")
    console.print(f"  URL: {doc.url}")


# Helper for col_to_letter
from gsuite_sheets.worksheet import Worksheet
