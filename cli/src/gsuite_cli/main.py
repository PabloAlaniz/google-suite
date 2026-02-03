"""Main CLI entry point using Typer."""

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli import auth, calendar, gmail, sheets

console = Console()
app = typer.Typer(
    name="gsuite",
    help="Google Suite CLI - Unified access to Gmail, Calendar, Drive",
    no_args_is_help=True,
)

# Register sub-commands
app.add_typer(auth.app, name="auth", help="Authentication management")
app.add_typer(gmail.app, name="gmail", help="Gmail operations")
app.add_typer(calendar.app, name="calendar", help="Calendar operations")
app.add_typer(sheets.app, name="sheets", help="Sheets operations")


@app.command()
def status():
    """Show overall status of Google Suite CLI."""
    from gsuite_core import GoogleAuth, get_settings

    settings = get_settings()
    auth = GoogleAuth()

    table = Table(title="Google Suite Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Version", "0.1.0")
    table.add_row("Credentials File", settings.credentials_file)
    table.add_row("Token Storage", settings.token_storage)
    table.add_row("Authenticated", "✓ Yes" if auth.is_authenticated() else "✗ No")

    if auth.is_authenticated():
        email = auth.get_user_email()
        if email:
            table.add_row("User", email)

    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8080, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the unified API server."""
    import uvicorn

    console.print(f"[green]Starting Google Suite API on {host}:{port}[/green]")
    console.print(f"[dim]Docs: http://{host}:{port}/docs[/dim]")

    uvicorn.run(
        "gsuite_api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
