"""Authentication CLI commands."""

import typer
from google.oauth2.credentials import Credentials
from rich.console import Console
from rich.panel import Panel

from gsuite_cli.output import print_json
from gsuite_core import (
    CredentialsNotFoundError,
    GoogleAuth,
    GSuiteError,
    Scopes,
    TokenRefreshError,
)

console = Console()
app = typer.Typer(no_args_is_help=True)


SCOPE_SETS = {
    "default": Scopes.default,
    "gmail": Scopes.gmail,
    "calendar": Scopes.calendar,
    "drive": Scopes.drive,
    "sheets": Scopes.sheets,
    "tasks": Scopes.tasks,
    "contacts": Scopes.contacts,
    "searchconsole": Scopes.searchconsole,
    "analytics": Scopes.analytics,
    "tagmanager": Scopes.tagmanager,
    "marketing": Scopes.marketing,
    "all": Scopes.all,
}


def _resolve_scopes(value: str) -> list[str]:
    """Union of the named scope sets, in order. An unknown name is an error, not the default."""
    selected: list[str] = []
    for name in (n.strip().lower() for n in value.split(",") if n.strip()):
        if name not in SCOPE_SETS:
            console.print(f"[red]Unknown scope set: {name}.[/red] Use: {', '.join(SCOPE_SETS)}")
            raise typer.Exit(1)
        selected += [s for s in SCOPE_SETS[name]() if s not in selected]
    return selected or Scopes.default()


@app.command()
def login(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-authentication"),
    scopes: str = typer.Option(
        "default",
        "--scopes",
        "-s",
        help=(
            "Comma-separated: default, gmail, calendar, drive, sheets, tasks, contacts, "
            "searchconsole, analytics, tagmanager, marketing (the three read-only), all "
            "(e.g. default,tasks or default,marketing). A new login replaces the stored "
            "scopes, so list every set you still need."
        ),
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help=(
            "For a machine without a browser (SSH, a server): print the consent URL to open "
            "elsewhere, then paste back the address the browser ends on (or its code)."
        ),
    ),
) -> None:
    """Authenticate with Google.

    Opens a browser window for OAuth consent, or with --no-browser prints the
    URL and asks for what the browser lands on.
    """
    selected_scopes = _resolve_scopes(scopes)

    auth = GoogleAuth(scopes=selected_scopes)

    try:
        if no_browser:
            credentials = _login_without_browser(auth, force)
        else:
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
        raise typer.Exit(1) from None
    except GSuiteError as e:
        console.print(f"[red]✗ {e.message}[/red]")
        if e.cause:
            console.print(f"[dim]Cause: {e.cause}[/dim]")
        raise typer.Exit(1) from None
    except Exception as e:  # noqa: BLE001 - last resort: report any failure, exit 1
        console.print(f"[red]✗ Authentication failed: {e}[/red]")
        raise typer.Exit(1) from None


def _login_without_browser(auth: GoogleAuth, force: bool) -> Credentials:
    """The two-step login: show the URL, read back the code or redirect URL."""
    credentials = auth.credentials
    if not force and credentials is not None:
        if auth.is_authenticated():
            return credentials
        if auth.needs_refresh() and auth.refresh():
            return credentials
    request = auth.start_authorization()
    console.print(
        Panel.fit(
            "1. Open this URL in any browser and allow access:\n\n"
            f"[link]{request.url}[/link]\n\n"
            "2. The browser ends on a page that doesn't load (http://localhost/...).\n"
            "   Copy that whole address and paste it below.",
            title="Google Suite Auth",
        )
    )
    pasted = typer.prompt("Address (or code)")
    return auth.finish_authorization(request, pasted)


@app.command()
def logout(
    local_only: bool = typer.Option(
        False, "--local-only", help="Only delete the stored token; don't revoke it at Google."
    ),
) -> None:
    """Revoke access at Google and delete the stored credentials."""
    auth = GoogleAuth()

    if auth.revoke(remote=not local_only):
        console.print("[green]✓ Logged out successfully[/green]")
    else:
        console.print("[yellow]No credentials to revoke[/yellow]")


@app.command()
def status() -> None:
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
def refresh() -> None:
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
        raise typer.Exit(1) from None


@app.command("export")
def export_token() -> None:
    """Export token as JSON (for migration to Cloud Run)."""
    auth = GoogleAuth()

    # Force load credentials from store
    _ = auth.credentials

    token_data = auth.export_token()
    if token_data:
        print_json(token_data)
    else:
        console.print("[red]No token to export[/red]")
        raise typer.Exit(1)
