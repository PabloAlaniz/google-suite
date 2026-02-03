"""Authentication CLI commands."""

import json

import typer
from rich.console import Console
from rich.panel import Panel

from gsuite_core import (
    CredentialsNotFoundError,
    GoogleAuth,
    GSuiteError,
    Scopes,
    TokenRefreshError,
)

console = Console()
app = typer.Typer(no_args_is_help=True)


@app.command()
def login(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-authentication"),
    scopes: str = typer.Option(
        "default", "--scopes", "-s", help="Scopes: default, gmail, calendar, drive, all"
    ),
):
    """
    Authenticate with Google (opens browser).

    This will open a browser window for OAuth consent.
    """
    scope_map = {
        "default": Scopes.default(),
        "gmail": Scopes.gmail(),
        "calendar": Scopes.calendar(),
        "drive": Scopes.drive(),
        "all": Scopes.all(),
    }

    selected_scopes = scope_map.get(scopes, Scopes.default())

    auth = GoogleAuth(scopes=selected_scopes)

    try:
        with console.status("[bold green]Opening browser for authentication..."):
            credentials = auth.authenticate(force=force)

        console.print(
            Panel.fit(
                "[green]✓ Authentication successful![/green]\n\n"
                f"Scopes: {', '.join(credentials.scopes or [])}",
                title="Google Suite Auth",
            )
        )

    except CredentialsNotFoundError as e:
        console.print(f"[red]✗ {e.message}[/red]")
        console.print(
            "\n[dim]Download from: Google Cloud Console → APIs & Services → Credentials[/dim]"
        )
        raise typer.Exit(1)
    except GSuiteError as e:
        console.print(f"[red]✗ {e.message}[/red]")
        if e.cause:
            console.print(f"[dim]Cause: {e.cause}[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Authentication failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def logout():
    """Revoke and delete stored credentials."""
    auth = GoogleAuth()

    if auth.revoke():
        console.print("[green]✓ Logged out successfully[/green]")
    else:
        console.print("[yellow]No credentials to revoke[/yellow]")


@app.command()
def status():
    """Check authentication status."""
    auth = GoogleAuth()

    if auth.is_authenticated():
        email = auth.get_user_email()
        console.print("[green]✓ Authenticated[/green]")
        if email:
            console.print(f"  User: {email}")
    elif auth.needs_refresh():
        console.print("[yellow]⚠ Token expired, needs refresh[/yellow]")
        console.print("  Run: gsuite auth login")
    else:
        console.print("[red]✗ Not authenticated[/red]")
        console.print("  Run: gsuite auth login")


@app.command()
def refresh():
    """Refresh the OAuth access token."""
    auth = GoogleAuth()

    if not auth.needs_refresh():
        if auth.is_authenticated():
            console.print("[green]Token is still valid, no refresh needed[/green]")
        else:
            console.print("[red]No valid token to refresh. Run: gsuite auth login[/red]")
            raise typer.Exit(1)
        return

    try:
        if auth.refresh():
            console.print("[green]✓ Token refreshed successfully[/green]")
        else:
            console.print("[red]✗ Token refresh failed. Run: gsuite auth login[/red]")
            raise typer.Exit(1)
    except TokenRefreshError as e:
        console.print(f"[red]✗ Token refresh failed: {e.message}[/red]")
        if e.cause:
            console.print(f"[dim]Cause: {e.cause}[/dim]")
        console.print("\n[yellow]Run: gsuite auth login[/yellow]")
        raise typer.Exit(1)


@app.command("export")
def export_token():
    """Export token as JSON (for migration to Cloud Run)."""
    auth = GoogleAuth()

    # Force load credentials from store
    _ = auth.credentials

    token_data = auth.export_token()
    if token_data:
        console.print_json(json.dumps(token_data, indent=2))
    else:
        console.print("[red]No token to export[/red]")
        raise typer.Exit(1)
