"""Google Analytics 4 CLI commands (read-only)."""

import typer
from rich.console import Console
from rich.table import Table

from gsuite_analytics import Analytics, Report
from gsuite_cli.output import print_json, to_data
from gsuite_core import GoogleAuth

console = Console()
app = typer.Typer(no_args_is_help=True)

OUTPUT_OPTION = typer.Option("table", "--output", "-o", help="Output: table, json")
DIMENSION_OPTION = typer.Option([], "--dim", "-d", help="Dimension, e.g. date (repeatable)")
LIMIT_OPTION = typer.Option(100, "--limit", "-l", help="Max rows")


def get_analytics() -> Analytics:
    """Get authenticated Analytics client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print(
                "[red]Not authenticated. Run: gsuite auth login --scopes default,analytics[/red]"
            )
            raise typer.Exit(1)

    return Analytics(auth)


def _print_report(report: Report, title: str) -> None:
    if not report.rows:
        console.print("[yellow]No rows[/yellow]")
        return

    table = Table(title=f"{title} ({report.row_count} rows)")
    for d in report.dimensions:
        table.add_column(d, style="cyan")
    for m in report.metrics:
        table.add_column(m, justify="right")
    for r in report.rows:
        table.add_row(
            *(r.dimensions.get(d, "") for d in report.dimensions),
            *("" if (v := r.metrics.get(m)) is None else str(v) for m in report.metrics),
        )
    console.print(table)


@app.command("accounts")
def accounts(output: str = OUTPUT_OPTION) -> None:
    """List accounts and their properties (to find property IDs)."""
    summaries = get_analytics().account_summaries()

    if output == "json":
        print_json(to_data(summaries))
        return

    table = Table(title=f"Accounts ({len(summaries)})")
    table.add_column("Account", style="cyan")
    table.add_column("Property")
    table.add_column("Property ID", style="dim")
    for a in summaries:
        if not a.properties:
            table.add_row(a.display_name, "", "")
        for p in a.properties:
            table.add_row(a.display_name, p.display_name, p.property_id)
    console.print(table)


@app.command("properties")
def properties(
    account_id: str = typer.Argument(..., help='Account ID ("123" or "accounts/123")'),
    show_deleted: bool = typer.Option(False, "--deleted", help="Include deleted properties"),
    output: str = OUTPUT_OPTION,
) -> None:
    """List the properties of an account."""
    result = get_analytics().list_properties(account_id, show_deleted=show_deleted)

    if output == "json":
        print_json(to_data(result))
        return

    table = Table(title=f"Properties ({len(result)})")
    table.add_column("Name", style="cyan")
    table.add_column("Property ID", style="dim")
    table.add_column("Time zone")
    table.add_column("Currency")
    for p in result:
        table.add_row(p.display_name, p.property_id, p.time_zone or "", p.currency_code or "")
    console.print(table)


@app.command("report")
def report(
    property_id: str = typer.Argument(..., help="GA4 property ID"),
    metric: list[str] = typer.Option(
        ["activeUsers"], "--metric", "-m", help="Metric, e.g. sessions (repeatable)"
    ),
    dimension: list[str] = DIMENSION_OPTION,
    start: str = typer.Option(
        "28daysAgo", "--start", "-s", help="YYYY-MM-DD, today, yesterday or NdaysAgo"
    ),
    end: str = typer.Option("today", "--end", "-e", help="YYYY-MM-DD, today, yesterday"),
    limit: int = LIMIT_OPTION,
    order_by: str | None = typer.Option(None, "--order-by", help="Metric or dimension to sort"),
    ascending: bool = typer.Option(False, "--asc", help="Sort ascending (default descending)"),
    output: str = OUTPUT_OPTION,
) -> None:
    """Run a report (Data API runReport)."""
    result = get_analytics().run_report(
        property_id,
        dimension,
        metric,
        date_ranges=[(start, end)],
        limit=limit,
        order_by=order_by,
        descending=not ascending,
    )

    if output == "json":
        print_json(to_data(result))
        return

    _print_report(result, f"{start} → {end}")


@app.command("realtime")
def realtime(
    property_id: str = typer.Argument(..., help="GA4 property ID"),
    metric: list[str] = typer.Option(["activeUsers"], "--metric", "-m", help="Metric (repeatable)"),
    dimension: list[str] = DIMENSION_OPTION,
    limit: int = LIMIT_OPTION,
    output: str = OUTPUT_OPTION,
) -> None:
    """Realtime report (last 30 minutes)."""
    result = get_analytics().run_realtime_report(property_id, dimension, metric, limit=limit)

    if output == "json":
        print_json(to_data(result))
        return

    _print_report(result, "Last 30 minutes")
