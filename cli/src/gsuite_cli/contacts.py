"""Contacts CLI commands."""

import typer
from rich.console import Console
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_contacts import Contact, Contacts
from gsuite_core import GoogleAuth

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_contacts() -> Contacts:
    """Get authenticated Contacts client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print(
                "[red]Not authenticated. Run: gsuite auth login --scopes default,contacts[/red]"
            )
            raise typer.Exit(1)

    return Contacts(auth)


def _as_dict(c: Contact) -> dict:
    return {
        "id": c.id,
        "display_name": c.display_name,
        "given_name": c.given_name,
        "family_name": c.family_name,
        "emails": c.emails,
        "phones": c.phones,
        "organization": c.organization,
        "job_title": c.job_title,
        "notes": c.notes,
    }


def _print(contacts: list[Contact], output: str, title: str) -> None:
    if output == "json":
        print_json([_as_dict(c) for c in contacts])
        return

    if not contacts:
        console.print("[yellow]No contacts found[/yellow]")
        return

    table = Table(title=f"{title} ({len(contacts)})")
    table.add_column("Name", style="cyan")
    table.add_column("Email")
    table.add_column("Phone")
    table.add_column("ID", style="dim")
    for c in contacts:
        table.add_row(c.display_name or "", c.email or "", c.phone or "", c.id)
    console.print(table)


@app.command("list")
@app.command("ls", hidden=True)
def list_contacts(
    limit: int = typer.Option(100, "--limit", "-l", help="Max contacts"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """List contacts, by first name."""
    result = get_contacts().list_contacts(max_results=limit, sort_order="FIRST_NAME_ASCENDING")
    _print(result, output, "Contacts")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Start of a name, email, phone or organization"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results (up to 30)"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """Search contacts."""
    _print(get_contacts().search(query, max_results=limit), output, f"Contacts matching {query!r}")


@app.command("show")
def show(
    contact_id: str = typer.Argument(..., help="Contact ID (c123...)"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
) -> None:
    """Show a contact."""
    contact = get_contacts().get(contact_id)
    if contact is None:
        console.print(f"[red]Contact not found: {contact_id}[/red]")
        raise typer.Exit(1)

    if output == "json":
        print_json(_as_dict(contact))
        return

    console.print(f"[bold]{contact.display_name or '(no name)'}[/bold]  [dim]{contact.id}[/dim]")
    if contact.organization or contact.job_title:
        console.print(" · ".join(v for v in (contact.job_title, contact.organization) if v))
    for email in contact.emails:
        console.print(f"  ✉ {email}")
    for phone in contact.phones:
        console.print(f"  ☎ {phone}")
    if contact.notes:
        console.print(f"[dim]{contact.notes}[/dim]")


@app.command("add")
def add(
    given_name: str | None = typer.Option(None, "--given", "-g", help="Given name"),
    family_name: str | None = typer.Option(None, "--family", "-f", help="Family name"),
    email: list[str] | None = typer.Option(None, "--email", "-e", help="Email (repeatable)"),
    phone: list[str] | None = typer.Option(None, "--phone", "-p", help="Phone (repeatable)"),
    organization: str | None = typer.Option(None, "--org", help="Organization"),
    job_title: str | None = typer.Option(None, "--title", help="Job title"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Notes"),
) -> None:
    """Create a contact (needs a name, an email or a phone)."""
    contact = get_contacts().create(
        given_name=given_name,
        family_name=family_name,
        emails=email or None,
        phones=phone or None,
        organization=organization,
        job_title=job_title,
        notes=notes,
    )
    console.print(
        f"[green]✓ Created[/green] {contact.display_name or contact.email or ''} "
        f"[dim]{contact.id}[/dim]"
    )


@app.command("delete")
@app.command("rm", hidden=True)
def remove(
    contact_id: str = typer.Argument(..., help="Contact ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
) -> None:
    """Delete a contact."""
    if not yes:
        typer.confirm(f"Delete contact {contact_id}? This can't be undone", abort=True)
    if not get_contacts().delete(contact_id):
        console.print(f"[red]Contact not found: {contact_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Deleted[/green] {contact_id}")
