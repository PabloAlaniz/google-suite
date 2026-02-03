"""Calendar CLI commands."""

import json
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from gsuite_calendar import Calendar
from gsuite_core import GoogleAuth

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_calendar() -> Calendar:
    """Get authenticated Calendar client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print("[red]Not authenticated. Run: gsuite auth login[/red]")
            raise typer.Exit(1)

    return Calendar(auth)


@app.command("list")
def list_events(
    days: int = typer.Option(7, "--days", "-d", help="Days ahead"),
    calendar_id: str | None = typer.Option(None, "--calendar", "-c", help="Calendar ID"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max events"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
):
    """List upcoming calendar events."""
    cal = get_calendar()

    with console.status("[bold green]Fetching events..."):
        events = cal.get_upcoming(days=days, calendar_id=calendar_id, max_results=limit)

    if output == "json":
        data = [
            {
                "id": e.id,
                "summary": e.summary,
                "start": e.start.isoformat() if e.start else None,
                "end": e.end.isoformat() if e.end else None,
                "location": e.location,
                "all_day": e.all_day,
            }
            for e in events
        ]
        console.print(json.dumps(data, indent=2))
    else:
        if not events:
            console.print("[yellow]No upcoming events[/yellow]")
            return

        table = Table(title=f"Events - Next {days} days ({len(events)})")
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Time", width=12)
        table.add_column("Event")
        table.add_column("Location", style="dim")

        for event in events:
            if event.all_day:
                date_str = event.start.strftime("%Y-%m-%d") if event.start else ""
                time_str = "All day"
            else:
                date_str = event.start.strftime("%Y-%m-%d") if event.start else ""
                time_str = event.start.strftime("%H:%M") if event.start else ""
                if event.end:
                    time_str += f"-{event.end.strftime('%H:%M')}"

            location = (event.location or "")[:20]
            table.add_row(date_str, time_str, event.summary, location)

        console.print(table)


@app.command()
def today(
    calendar_id: str | None = typer.Option(None, "--calendar", "-c", help="Calendar ID"),
):
    """Show today's events."""
    cal = get_calendar()

    with console.status("[bold green]Fetching today's events..."):
        events = cal.get_today(calendar_id=calendar_id)

    if not events:
        console.print("[green]No events scheduled for today[/green]")
        return

    console.print(f"[bold]Today's Events ({len(events)})[/bold]\n")

    for event in events:
        if event.all_day:
            time_str = "📅 All day"
        else:
            time_str = f"🕐 {event.start.strftime('%H:%M')}" if event.start else ""
            if event.end:
                time_str += f" - {event.end.strftime('%H:%M')}"

        console.print(f"  {time_str}")
        console.print(f"  [bold]{event.summary}[/bold]")
        if event.location:
            console.print(f"  📍 {event.location}")
        console.print()


@app.command()
def create(
    summary: str = typer.Argument(..., help="Event title"),
    start: str = typer.Option(
        ..., "--start", "-s", help="Start time (YYYY-MM-DD HH:MM or YYYY-MM-DD)"
    ),
    end: str | None = typer.Option(None, "--end", "-e", help="End time"),
    description: str | None = typer.Option(None, "--desc", "-d", help="Description"),
    location: str | None = typer.Option(None, "--location", "-l", help="Location"),
    calendar_id: str | None = typer.Option(None, "--calendar", "-c", help="Calendar ID"),
    all_day: bool = typer.Option(False, "--all-day", help="All-day event"),
):
    """Create a new calendar event."""
    cal = get_calendar()

    # Parse start time
    try:
        if " " in start:
            start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
        else:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            all_day = True
    except ValueError:
        console.print("[red]Invalid start format. Use: YYYY-MM-DD HH:MM or YYYY-MM-DD[/red]")
        raise typer.Exit(1)

    # Parse end time
    end_dt = None
    if end:
        try:
            if " " in end:
                end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
            else:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Invalid end format[/red]")
            raise typer.Exit(1)

    with console.status("[bold green]Creating event..."):
        event = cal.create_event(
            summary=summary,
            start=start_dt,
            end=end_dt,
            description=description,
            location=location,
            calendar_id=calendar_id,
            all_day=all_day,
        )

    console.print("[green]✓ Event created![/green]")
    console.print(f"  ID: {event.id}")
    console.print(f"  Title: {event.summary}")
    if event.html_link:
        console.print(f"  Link: {event.html_link}")


@app.command()
def delete(
    event_id: str = typer.Argument(..., help="Event ID to delete"),
    calendar_id: str | None = typer.Option(None, "--calendar", "-c", help="Calendar ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a calendar event."""
    if not confirm:
        confirm = typer.confirm("Are you sure you want to delete this event?")
        if not confirm:
            raise typer.Abort()

    cal = get_calendar()

    if cal.delete_event(event_id, calendar_id=calendar_id):
        console.print("[green]✓ Event deleted[/green]")
    else:
        console.print("[red]Failed to delete event[/red]")
        raise typer.Exit(1)


@app.command()
def calendars():
    """List all accessible calendars."""
    cal = get_calendar()

    with console.status("[bold green]Fetching calendars..."):
        all_calendars = cal.get_calendars()

    table = Table(title="Calendars")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Access", style="green")
    table.add_column("Primary")

    for c in all_calendars:
        primary = "★" if c.primary else ""
        table.add_row(c.summary, c.id[:40], c.access_role, primary)

    console.print(table)


@app.command()
def week():
    """Show this week's events."""
    cal = get_calendar()

    with console.status("[bold green]Fetching week's events..."):
        events = cal.get_upcoming(days=7)

    if not events:
        console.print("[green]No events this week[/green]")
        return

    # Group by day
    by_day = {}
    for event in events:
        if event.start:
            day_key = event.start.strftime("%Y-%m-%d")
            if day_key not in by_day:
                by_day[day_key] = []
            by_day[day_key].append(event)

    for day, day_events in sorted(by_day.items()):
        day_dt = datetime.strptime(day, "%Y-%m-%d")
        day_name = day_dt.strftime("%A, %B %d")

        console.print(f"\n[bold cyan]{day_name}[/bold cyan]")

        for event in day_events:
            if event.all_day:
                time_str = "All day"
            else:
                time_str = event.start.strftime("%H:%M") if event.start else ""

            console.print(f"  {time_str:>8}  {event.summary}")
