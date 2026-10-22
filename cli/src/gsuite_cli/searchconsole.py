"""Search Console CLI commands (read-only)."""

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_core import GoogleAuth
from gsuite_searchconsole import SearchConsole

console = Console()
app = typer.Typer(no_args_is_help=True)

OUTPUT_OPTION = typer.Option("table", "--output", "-o", help="Output: table, json")


def get_searchconsole() -> SearchConsole:
    """Get authenticated Search Console client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print(
                "[red]Not authenticated. "
                "Run: gsuite auth login --scopes default,searchconsole[/red]"
            )
            raise typer.Exit(1)

    return SearchConsole(auth)


def _filter(value: str) -> dict[str, str]:
    """dimension:operator:expression, e.g. query:contains:shoes."""
    parts = value.split(":", 2)
    if len(parts) != 3 or not all(parts):
        raise typer.BadParameter(f"{value!r} is not dimension:operator:expression")
    dimension, operator, expression = parts
    return {"dimension": dimension, "operator": operator, "expression": expression}


@app.command("sites")
def sites(output: str = OUTPUT_OPTION) -> None:
    """List the properties you can see."""
    result = get_searchconsole().list_sites()

    if output == "json":
        print_json(result)
        return

    table = Table(title=f"Sites ({len(result)})")
    table.add_column("Site", style="cyan")
    table.add_column("Permission", style="dim")
    for s in result:
        table.add_row(s.get("siteUrl", ""), s.get("permissionLevel", ""))
    console.print(table)


@app.command("query")
def query(
    site_url: str = typer.Argument(..., help="Property, e.g. sc-domain:example.com"),
    start: str = typer.Option(..., "--start", "-s", help="Start day (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="End day (YYYY-MM-DD)"),
    dimension: list[str] = typer.Option(
        [], "--dim", "-d", help="query, page, country, device, date, searchAppearance (repeatable)"
    ),
    filters: list[str] = typer.Option(
        [],
        "--filter",
        "-f",
        help="dimension:operator:expression, e.g. query:contains:shoes (repeatable, ANDed)",
    ),
    search_type: str = typer.Option("web", "--type", help="web, image, video, news, discover"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max rows (1-25000)"),
    start_row: int = typer.Option(0, "--start-row", help="Row offset, for paging"),
    output: str = OUTPUT_OPTION,
) -> None:
    """Search analytics: clicks, impressions, CTR and position."""
    rows = get_searchconsole().query(
        site_url,
        start,
        end,
        dimensions=dimension,
        filters=[_filter(f) for f in filters],
        row_limit=limit,
        start_row=start_row,
        search_type=search_type,
    )

    if output == "json":
        print_json(rows)
        return

    if not rows:
        console.print("[yellow]No rows[/yellow]")
        return

    table = Table(title=f"{site_url} ({len(rows)} rows)")
    for d in dimension:
        table.add_column(d, style="cyan")
    for m in ("Clicks", "Impressions", "CTR", "Position"):
        table.add_column(m, justify="right")
    for r in rows:
        table.add_row(
            *(str(r.get(d, "")) for d in dimension),
            str(r["clicks"]),
            str(r["impressions"]),
            f"{r['ctr']:.1%}",
            f"{r['position']:.1f}",
        )
    console.print(table)


@app.command("inspect")
def inspect(
    site_url: str = typer.Argument(..., help="Property the URL belongs to"),
    url: str = typer.Argument(..., help="URL to inspect"),
    output: str = OUTPUT_OPTION,
) -> None:
    """URL Inspection: index status, canonical and last crawl."""
    result = get_searchconsole().inspect_url(site_url, url)

    if output == "json":
        print_json(result)
        return

    index = result.get("indexStatusResult", {})
    table = Table(title=url, show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for label, key in (
        ("Verdict", "verdict"),
        ("Coverage", "coverageState"),
        ("Indexing", "indexingState"),
        ("Page fetch", "pageFetchState"),
        ("Robots.txt", "robotsTxtState"),
        ("Last crawl", "lastCrawlTime"),
        ("Google canonical", "googleCanonical"),
        ("User canonical", "userCanonical"),
    ):
        table.add_row(label, str(index.get(key, "")))
    console.print(table)


@app.command("sitemaps")
def sitemaps(
    site_url: str = typer.Argument(..., help="Property, e.g. sc-domain:example.com"),
    output: str = OUTPUT_OPTION,
) -> None:
    """List the sitemaps submitted for a property."""
    result = get_searchconsole().list_sitemaps(site_url)

    if output == "json":
        print_json(result)
        return

    if not result:
        console.print("[yellow]No sitemaps[/yellow]")
        return

    table = Table(title=f"Sitemaps ({len(result)})")
    table.add_column("Path", style="cyan")
    table.add_column("Last downloaded")
    table.add_column("Errors", justify="right")
    table.add_column("Warnings", justify="right")
    for s in result:
        table.add_row(
            s.get("path", ""),
            s.get("lastDownloaded", ""),
            str(s.get("errors", 0)),
            str(s.get("warnings", 0)),
        )
    console.print(table)
