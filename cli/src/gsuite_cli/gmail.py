"""Gmail CLI commands."""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gsuite_cli.output import print_json
from gsuite_core import GoogleAuth
from gsuite_gmail import Gmail, Message

console = Console()
app = typer.Typer(no_args_is_help=True)


def get_gmail() -> Gmail:
    """Get authenticated Gmail client."""
    auth = GoogleAuth()

    if not auth.is_authenticated():
        if auth.needs_refresh():
            auth.refresh()
        else:
            console.print("[red]Not authenticated. Run: gsuite auth login[/red]")
            raise typer.Exit(1)

    return Gmail(auth)


@app.command("list")
def list_messages(
    query: str | None = typer.Option(None, "--query", "-q", help="Gmail search query"),
    unread: bool = typer.Option(False, "--unread", "-u", help="Only unread"),
    starred: bool = typer.Option(False, "--starred", "-s", help="Only starred"),
    from_addr: str | None = typer.Option(None, "--from", "-f", help="From address"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max messages"),
    output: str = typer.Option("table", "--output", "-o", help="Output: table, json"),
):
    """List Gmail messages."""
    gmail = get_gmail()

    # Build query
    query_parts = []
    if query:
        query_parts.append(query)
    if unread:
        query_parts.append("is:unread")
    if starred:
        query_parts.append("is:starred")
    if from_addr:
        query_parts.append(f"from:{from_addr}")

    final_query = " ".join(query_parts) if query_parts else None

    with console.status("[bold green]Fetching messages..."):
        messages = gmail.get_messages(query=final_query, max_results=limit)

    if output == "json":
        data = [
            {
                "id": m.id,
                "subject": m.subject,
                "from": m.sender,
                "date": m.date.isoformat() if m.date else None,
                "is_unread": m.is_unread,
                "is_starred": m.is_starred,
            }
            for m in messages
        ]
        print_json(data)
    else:
        if not messages:
            console.print("[yellow]No messages found[/yellow]")
            return

        table = Table(title=f"Messages ({len(messages)})")
        table.add_column("", width=2)
        table.add_column("Date", style="dim", width=16)
        table.add_column("From", width=25)
        table.add_column("Subject")

        for msg in messages:
            status = ""
            if msg.is_unread:
                status += "○"
            else:
                status += "●"
            if msg.is_starred:
                status += "★"

            date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""
            sender = msg.sender[:25] if len(msg.sender) > 25 else msg.sender
            subject = msg.subject[:50] if len(msg.subject) > 50 else msg.subject

            style = "bold" if msg.is_unread else ""
            table.add_row(status, date_str, sender, subject, style=style)

        console.print(table)


@app.command("read")
def read_message(
    message_id: str = typer.Argument(..., help="Message ID"),
    mark_read: bool = typer.Option(False, "--mark-read", "-r", help="Mark as read"),
    output: str = typer.Option("text", "--output", "-o", help="Output: text, json, html"),
):
    """Read a specific message."""
    gmail = get_gmail()

    with console.status("[bold green]Fetching message..."):
        message = gmail.get_message(message_id)

    if not message:
        console.print(f"[red]Message not found: {message_id}[/red]")
        raise typer.Exit(1)

    if output == "json":
        data = {
            "id": message.id,
            "thread_id": message.thread_id,
            "subject": message.subject,
            "from": message.sender,
            "to": message.recipient,
            "cc": message.cc,
            "date": message.date.isoformat() if message.date else None,
            "body": message.plain or message.html,
            "labels": message.labels,
            "attachments": [{"filename": a.filename, "size": a.size} for a in message.attachments],
        }
        print_json(data)
    elif output == "html":
        console.print(message.html or message.plain or "(no body)")
    else:
        # Rich formatted output
        console.print(
            Panel.fit(
                f"[bold]From:[/bold] {message.sender}\n"
                f"[bold]To:[/bold] {message.recipient}\n"
                f"[bold]Date:[/bold] {message.date}\n"
                f"[bold]Subject:[/bold] {message.subject}\n"
                f"[bold]Labels:[/bold] {', '.join(message.labels)}",
                title="Message Details",
            )
        )

        if message.attachments:
            console.print(f"\n[bold]Attachments ({len(message.attachments)}):[/bold]")
            for att in message.attachments:
                console.print(f"  📎 {att.filename} ({att.size} bytes)")

        console.print("\n[bold]Body:[/bold]")
        console.print(message.plain or message.html or "(no body)")

    if mark_read and message.is_unread:
        message.mark_as_read()
        console.print("\n[dim]Marked as read[/dim]")


@app.command()
def send(
    to: list[str] = typer.Option(..., "--to", "-t", help="Recipient(s)"),
    subject: str = typer.Option(..., "--subject", "-s", help="Subject"),
    body: str | None = typer.Option(None, "--body", "-b", help="Body (or pipe to stdin)"),
    cc: list[str] | None = typer.Option(None, "--cc", help="CC recipient(s)"),
    bcc: list[str] | None = typer.Option(None, "--bcc", help="BCC recipient(s)"),
    attach: list[Path] | None = typer.Option(
        None, "--attach", "-a", exists=True, dir_okay=False, help="File to attach (repeatable)"
    ),
    html: bool = typer.Option(False, "--html", help="Body is HTML"),
) -> None:
    """Send an email."""
    gmail = get_gmail()

    # Read body from stdin if not provided
    message_body = body
    if not message_body and not sys.stdin.isatty():
        message_body = sys.stdin.read()

    if not message_body:
        console.print("[red]Message body required (--body or pipe to stdin)[/red]")
        raise typer.Exit(1)

    with console.status("[bold green]Sending message..."):
        message = gmail.send(
            to=to,
            subject=subject,
            body=message_body,
            cc=cc,
            bcc=bcc,
            html=html,
            attachments=list(attach) if attach else None,
        )

    console.print(f"[green]✓ Message sent![/green] ID: {message.id}")


@app.command()
def reply(
    message_id: str = typer.Argument(..., help="Message ID to reply to"),
    body: str | None = typer.Option(None, "--body", "-b", help="Body (or pipe to stdin)"),
    reply_all: bool = typer.Option(False, "--all", help="Reply to all recipients"),
    attach: list[Path] | None = typer.Option(
        None, "--attach", "-a", exists=True, dir_okay=False, help="File to attach (repeatable)"
    ),
) -> None:
    """Reply in the same thread."""
    gmail = get_gmail()

    message_body = body
    if not message_body and not sys.stdin.isatty():
        message_body = sys.stdin.read()
    if not message_body:
        console.print("[red]Message body required (--body or pipe to stdin)[/red]")
        raise typer.Exit(1)

    original = gmail.get_message(message_id)
    if original is None:
        console.print(f"[red]Message not found: {message_id}[/red]")
        raise typer.Exit(1)

    with console.status("[bold green]Sending reply..."):
        sent = gmail.reply(
            original,
            message_body,
            reply_all=reply_all,
            attachments=list(attach) if attach else None,
        )

    console.print(f"[green]✓ Reply sent![/green] ID: {sent.id}")


@app.command()
def labels():
    """List all Gmail labels."""
    gmail = get_gmail()

    with console.status("[bold green]Fetching labels..."):
        all_labels = gmail.get_labels()

    table = Table(title="Labels")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Unread", justify="right")
    table.add_column("Total", justify="right")

    for label in sorted(all_labels, key=lambda l: (l.type.value, l.name)):
        unread = str(label.messages_unread) if label.messages_unread else ""
        table.add_row(label.name, label.type.value, unread, str(label.messages_total))

    console.print(table)


@app.command()
def search(
    query_str: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
):
    """Search messages with Gmail query syntax."""
    gmail = get_gmail()

    console.print(f"[dim]Search: {query_str}[/dim]\n")

    with console.status("[bold green]Searching..."):
        messages = gmail.search(query_str, max_results=limit)

    if not messages:
        console.print("[yellow]No messages found[/yellow]")
        return

    table = Table(title=f"Results ({len(messages)})")
    table.add_column("", width=2)
    table.add_column("Date", style="dim", width=16)
    table.add_column("From", width=25)
    table.add_column("Subject")

    for msg in messages:
        status = "○" if msg.is_unread else "●"
        if msg.is_starred:
            status += "★"

        date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""
        table.add_row(status, date_str, msg.sender[:25], msg.subject[:50])

    console.print(table)


@app.command()
def profile():
    """Show Gmail profile info."""
    gmail = get_gmail()

    profile = gmail.get_profile()

    table = Table(title="Gmail Profile")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Email", profile.get("emailAddress", ""))
    table.add_row("Messages Total", f"{profile.get('messagesTotal', 0):,}")
    table.add_row("Threads Total", f"{profile.get('threadsTotal', 0):,}")
    table.add_row("History ID", profile.get("historyId", ""))

    console.print(table)


def _get_or_exit(gmail: Gmail, message_id: str) -> Message:
    message = gmail.get_message(message_id)
    if message is None:
        console.print(f"[red]Message not found: {message_id}[/red]")
        raise typer.Exit(1)
    return message


@app.command()
def mark(
    message_id: str = typer.Argument(..., help="Message ID"),
    read: bool = typer.Option(False, "--read", help="Mark as read"),
    unread: bool = typer.Option(False, "--unread", help="Mark as unread"),
    star: bool = typer.Option(False, "--star", help="Star"),
    unstar: bool = typer.Option(False, "--unstar", help="Remove star"),
) -> None:
    """Mark a message read/unread or (un)starred."""
    if read and unread or star and unstar or not (read or unread or star or unstar):
        console.print("[red]Give one of --read/--unread and/or one of --star/--unstar[/red]")
        raise typer.Exit(2)

    gmail = get_gmail()
    add = ["UNREAD"] if unread else []
    remove = ["UNREAD"] if read else []
    add += ["STARRED"] if star else []
    remove += ["STARRED"] if unstar else []
    gmail.batch_modify([message_id], add_labels=add, remove_labels=remove)
    console.print(f"[green]✓ Updated {message_id}[/green]")


@app.command()
def archive(message_id: str = typer.Argument(..., help="Message ID")) -> None:
    """Remove a message from the inbox."""
    get_gmail().batch_modify([message_id], remove_labels=["INBOX"])
    console.print(f"[green]✓ Archived {message_id}[/green]")


@app.command()
def trash(message_id: str = typer.Argument(..., help="Message ID")) -> None:
    """Move a message to the trash."""
    _get_or_exit(get_gmail(), message_id).trash()
    console.print(f"[green]✓ Trashed {message_id}[/green]")
