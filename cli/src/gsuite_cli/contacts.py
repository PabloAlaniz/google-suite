"""Contacts CLI commands."""

from typing import Any

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


def _as_dict(c: Contact) -> dict[str, Any]:
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


groups_app = typer.Typer(no_args_is_help=True, help="Contact groups (labels)")
app.add_typer(groups_app, name="groups")


@groups_app.command("list")
def list_groups(
    output: str = typer.Option("table", "--output", "-o", help="table or json"),
) -> None:
    """List contact groups, system groups included."""
    groups = get_contacts().list_groups()
    if output == "json":
        print_json(
            [
                {"id": g.id, "name": g.name, "type": g.group_type, "members": g.member_count}
                for g in groups
            ]
        )
        return
    table = Table(title=f"Groups ({len(groups)})")
    table.add_column("Name", style="cyan")
    table.add_column("Members", justify="right")
    table.add_column("ID", style="dim")
    for g in groups:
        table.add_row(
            g.name + (" [dim](system)[/dim]" if g.is_system else ""), str(g.member_count), g.id
        )
    console.print(table)


@groups_app.command("create")
def create_group(name: str = typer.Argument(..., help="Group name")) -> None:
    """Create a contact group."""
    group = get_contacts().create_group(name)
    console.print(f"[green]✓ Created[/green] {group.name} [dim]{group.id}[/dim]")


@groups_app.command("delete")
def delete_group(
    group_id: str = typer.Argument(..., help="Group ID"),
    with_contacts: bool = typer.Option(
        False, "--with-contacts", help="Also delete the contacts in it"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
) -> None:
    """Delete a group (its contacts stay unless --with-contacts)."""
    if not yes:
        what = "and its contacts " if with_contacts else ""
        typer.confirm(f"Delete group {group_id} {what}? This can't be undone", abort=True)
    if not get_contacts().delete_group(group_id, delete_contacts=with_contacts):
        console.print(f"[red]Group not found: {group_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✓ Deleted[/green] {group_id}")


@groups_app.command("members")
def group_members(
    group_id: str = typer.Argument(..., help="Group ID"),
    output: str = typer.Option("table", "--output", "-o", help="table or json"),
) -> None:
    """The contacts in a group."""
    client = get_contacts()
    _print(client.get_many(client.group_members(group_id)), output, f"Group {group_id}")


def _modify(group_id: str, add: list[str], remove: list[str]) -> None:
    skipped = get_contacts().modify_group(group_id, add=add, remove=remove)
    changed = len(add) + len(remove) - len(skipped)
    console.print(f"[green]✓ Updated[/green] {changed} contact(s) in {group_id}")
    if skipped:
        console.print(f"[yellow]Left as they were:[/yellow] {', '.join(skipped)}")


@groups_app.command("add")
def add_to_group(
    group_id: str = typer.Argument(..., help="Group ID"),
    contact_ids: list[str] = typer.Argument(..., help="Contact IDs"),
) -> None:
    """Add contacts to a group."""
    _modify(group_id, contact_ids, [])


@groups_app.command("remove")
def remove_from_group(
    group_id: str = typer.Argument(..., help="Group ID"),
    contact_ids: list[str] = typer.Argument(..., help="Contact IDs"),
) -> None:
    """Remove contacts from a group (they stay in your contacts)."""
    _modify(group_id, [], contact_ids)
