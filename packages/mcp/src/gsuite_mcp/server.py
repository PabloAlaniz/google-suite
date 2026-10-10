"""MCP server for gsuite-sdk: Gmail, Calendar, Drive, Sheets, Tasks and Contacts tools.

Runs over stdio (``gsuite-mcp``) and reuses the login of ``gsuite auth login``
(GSUITE_TOKEN_DB_PATH / GSUITE_CREDENTIALS_FILE). Tools are annotated so
clients can tell read-only ones from those that send, share or delete.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from gsuite_core import __version__
from gsuite_core.exceptions import GSuiteError, PermissionDeniedError
from gsuite_mcp.serialize import message_full, message_summary, to_json
from gsuite_mcp.services import Services

INSTRUCTIONS = """\
Google Workspace for the signed-in user: Gmail, Calendar, Drive, Sheets, Tasks
and Contacts. Read tools are safe to call freely. Ask the user before tools
that send email, invite attendees, share files or delete anything. Dates are
ISO 8601 (2026-03-01 or 2026-03-01T10:00); times without an offset use the
server's GSUITE_DEFAULT_TIMEZONE (UTC by default). If a tool says there is no
login, tell the user to run `gsuite auth login`."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

SendUpdates = Literal["all", "externalOnly", "none"]
F = TypeVar("F", bound=Callable[..., Any])


def sdk_errors(func: F) -> F:
    """SDK errors become tool errors the agent can read."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except PermissionDeniedError as exc:
            raise ToolError(
                f"{exc.message}. Usually a scope missing from the login: run "
                "`gsuite auth login --force --scopes default,tasks,contacts`."
            ) from exc
        except GSuiteError as exc:
            raise ToolError(f"{type(exc).__name__}: {exc.message}") from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def results(items: list[Any]) -> dict[str, Any]:
    """One object for list results (a bare list becomes one content block per item)."""
    return {"count": len(items), "results": items}


def parse_when(value: str) -> datetime | date:
    """ "2026-03-01" -> date; "2026-03-01T10:00" / "2026-03-01 10:00" -> datetime."""
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(f"{value!r} is not an ISO date or datetime") from exc


def parse_day(value: str | None) -> date | None:
    if value is None:
        return None
    when = parse_when(value)
    return when.date() if isinstance(when, datetime) else when


def build_server(services: Services | None = None) -> MCPServer:
    """The MCP server; tests pass Services built on mocked clients."""
    svc = services or Services()
    server = MCPServer(
        "gsuite-sdk",
        title="Google Workspace (gsuite-sdk)",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://pabloalaniz.github.io/google-suite/",
    )

    def tool(annotations: ToolAnnotations) -> Callable[[F], F]:
        def register(func: F) -> F:
            server.tool(annotations=annotations)(sdk_errors(func))
            return func

        return register

    # ------------------------------------------------------------- auth

    @tool(READ)
    def auth_status() -> dict[str, Any]:
        """Whether the server has a valid Google login, and for which account and scopes."""
        auth = svc.auth()
        credentials = auth.credentials
        return {
            "authenticated": True,
            "email": auth.get_user_email(),
            "scopes": sorted(credentials.scopes or []) if credentials else [],
        }

    # ------------------------------------------------------------ gmail

    @tool(READ)
    def gmail_search(query: str, max_results: int = 10) -> dict[str, Any]:
        """Search Gmail with Gmail query syntax (from:, to:, subject:, is:unread,
        has:attachment, newer_than:7d, label:...). Returns summaries without bodies."""
        return results(
            [message_summary(m) for m in svc.gmail.search(query, max_results=max_results)]
        )

    @tool(READ)
    def gmail_read(message_id: str) -> dict[str, Any]:
        """Read one email: headers, text body and attachment list."""
        message = svc.gmail.get_message(message_id)
        if message is None:
            raise ToolError(f"No message {message_id}")
        return message_full(message)

    @tool(WRITE)
    def gmail_send(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
    ) -> dict[str, Any]:
        """Send an email. Confirm recipients and content with the user first."""
        sent = svc.gmail.send(to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_reply(message_id: str, body: str, reply_all: bool = False) -> dict[str, Any]:
        """Reply in the thread of a message. Confirm the content with the user first."""
        message = svc.gmail.get_message(message_id)
        if message is None:
            raise ToolError(f"No message {message_id}")
        sent = svc.gmail.reply(message, body, reply_all=reply_all)
        return {"id": sent.id, "thread_id": sent.thread_id}

    @tool(WRITE)
    def gmail_create_draft(
        to: list[str], subject: str, body: str, cc: list[str] | None = None
    ) -> dict[str, Any]:
        """Save a draft without sending it (safe way to propose an email)."""
        draft = svc.gmail.create_draft(to=to, subject=subject, body=body, cc=cc)
        return {"draft_id": draft.id}

    # --------------------------------------------------------- calendar

    @tool(READ)
    def calendar_list_events(
        days: int = 7, calendar_id: str | None = None, max_results: int = 50
    ) -> dict[str, Any]:
        """Events from now until `days` ahead."""
        events = svc.calendar.get_upcoming(
            days=days, calendar_id=calendar_id, max_results=max_results
        )
        return results(to_json(events))

    @tool(WRITE)
    def calendar_create_event(
        summary: str,
        start: str,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        meet: bool = False,
        send_updates: SendUpdates = "none",
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an event. `start`/`end` are ISO; a date alone makes an all-day event.
        `meet` adds a Google Meet link; `send_updates="all"` emails the attendees
        (confirm with the user first)."""
        start_at = parse_when(start)
        event = svc.calendar.create_event(
            summary=summary,
            start=start_at,
            end=parse_when(end) if end else None,
            description=description,
            location=location,
            attendees=attendees,
            all_day=not isinstance(start_at, datetime),
            meet=meet,
            send_updates=send_updates,
            calendar_id=calendar_id,
        )
        return to_json(event)  # type: ignore[no-any-return]

    @tool(DESTRUCTIVE)
    def calendar_delete_event(
        event_id: str, send_updates: SendUpdates = "none", calendar_id: str | None = None
    ) -> dict[str, Any]:
        """Delete an event. Confirm with the user first."""
        deleted = svc.calendar.delete_event(
            event_id, calendar_id=calendar_id, send_updates=send_updates
        )
        if not deleted:
            raise ToolError(f"No event {event_id}")
        return {"deleted": event_id}

    @tool(READ)
    def calendar_free_busy(
        time_min: str, time_max: str, calendars: list[str] | None = None
    ) -> dict[str, Any]:
        """Busy intervals per calendar (default: the user's) between two ISO datetimes."""
        start, end = parse_when(time_min), parse_when(time_max)
        if not (isinstance(start, datetime) and isinstance(end, datetime)):
            raise ToolError("time_min and time_max need a time, e.g. 2026-03-02T09:00")
        return to_json(svc.calendar.get_free_busy(start, end, calendars=calendars))  # type: ignore[no-any-return]

    # ------------------------------------------------------------ drive

    @tool(READ)
    def drive_search(
        name: str | None = None, query: str | None = None, max_results: int = 20
    ) -> dict[str, Any]:
        """Find files by name (contains) or with a raw Drive query
        (e.g. "mimeType = 'application/pdf' and modifiedTime > '2026-01-01'")."""
        if name and not query:
            files = svc.drive.search(name)[:max_results]
        else:
            files = svc.drive.list_files(query=query, max_results=max_results)
        return results(to_json(files))

    @tool(READ)
    def drive_read_file(file_id: str, max_chars: int = 20000) -> dict[str, Any]:
        """Text of a file: Google Docs/Slides as text, Google Sheets as CSV, and
        plain-text files as they are. Binary files (PDF, images) are refused."""
        file = svc.drive.get(file_id)
        if file is None:
            raise ToolError(f"No file {file_id}")
        mime = file.mime_type
        if mime == "application/vnd.google-apps.spreadsheet":
            text = svc.drive.export(file_id, "csv").decode("utf-8", "replace")
        elif mime.startswith("application/vnd.google-apps."):
            text = svc.drive.export(file_id, "txt").decode("utf-8", "replace")
        elif mime.startswith("text/") or mime in ("application/json", "application/xml"):
            text = svc.drive.get_content(file_id).decode("utf-8", "replace")
        else:
            raise ToolError(
                f"{file.name} is {mime}, not text. Download it with "
                f"`gsuite drive download {file_id}` instead."
            )
        return {
            "id": file.id,
            "name": file.name,
            "mime_type": mime,
            "truncated": len(text) > max_chars,
            "text": text[:max_chars],
        }

    @tool(WRITE)
    def drive_upload(
        path: str, parent_id: str | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Upload a local file (path on the machine running this server)."""
        return to_json(svc.drive.upload(path, name=name, parent_id=parent_id))  # type: ignore[no-any-return]

    @tool(WRITE)
    def drive_share(
        file_id: str,
        email: str | None = None,
        role: Literal["reader", "commenter", "writer"] = "reader",
        anyone: bool = False,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Share a file with a person (email) or with anyone who has the link
        (anyone=true). Confirm with the user first."""
        if not email and not anyone:
            raise ToolError("Give an email, or anyone=true for a link anyone can open")
        permission = svc.drive.add_permission(
            file_id,
            role=role,
            type="anyone" if anyone else "user",
            email=email,
            notify=notify,
        )
        return to_json(permission)  # type: ignore[no-any-return]

    # ----------------------------------------------------------- sheets

    def open_spreadsheet(spreadsheet: str) -> Any:
        """By URL, ID or exact title."""
        if spreadsheet.startswith("http"):
            return svc.sheets.open_by_url(spreadsheet)
        if len(spreadsheet) > 30:
            return svc.sheets.open_by_key(spreadsheet)
        return svc.sheets.open(spreadsheet)

    def worksheet(spreadsheet: str, sheet: str | None) -> Any:
        doc = open_spreadsheet(spreadsheet)
        ws = doc.worksheet(sheet) if sheet else doc.sheet1
        if ws is None:
            raise ToolError(f"No tab {sheet!r} in {doc.title}")
        return ws

    @tool(READ)
    def sheets_read(
        spreadsheet: str, range: str = "A1:Z200", sheet: str | None = None
    ) -> dict[str, Any]:
        """Read a range. `spreadsheet` is a URL, an ID or an exact title; `sheet`
        is the tab (default: the first one). Values come back as displayed."""
        ws = worksheet(spreadsheet, sheet)
        return {"sheet": ws.title, "range": range, "values": ws.get(range)}

    @tool(WRITE)
    def sheets_append(
        spreadsheet: str, rows: list[list[Any]], sheet: str | None = None
    ) -> dict[str, Any]:
        """Append rows after the last one with data."""
        ws = worksheet(spreadsheet, sheet)
        ws.append_rows(rows)
        return {"sheet": ws.title, "appended": len(rows)}

    @tool(DESTRUCTIVE)
    def sheets_update(
        spreadsheet: str, range: str, values: list[list[Any]], sheet: str | None = None
    ) -> dict[str, Any]:
        """Overwrite a range starting at `range` (e.g. "B2") with a 2D list of values."""
        ws = worksheet(spreadsheet, sheet)
        ws.update(range, values)
        return {"sheet": ws.title, "range": range, "rows": len(values)}

    @tool(WRITE)
    def sheets_upsert(
        spreadsheet: str, rows: list[dict[str, Any]], key: str, sheet: str | None = None
    ) -> dict[str, Any]:
        """Update the rows whose `key` column matches and append the rest.
        The first row of the sheet is the header; rows are {column: value}."""
        ws = worksheet(spreadsheet, sheet)
        return dict(ws.upsert(rows, key=key))

    # ------------------------------------------------------------ tasks

    @tool(READ)
    def tasks_list(
        tasklist_id: str = "@default",
        show_completed: bool = False,
        due_before: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Tasks of a list (default: the user's main list), pending only unless
        show_completed. Needs the Tasks scope."""
        tasks = svc.tasks.list_tasks(
            tasklist_id,
            show_completed=show_completed,
            due_max=parse_day(due_before),
            max_results=max_results,
        )
        return results(to_json(tasks))

    @tool(WRITE)
    def tasks_add(
        title: str,
        notes: str | None = None,
        due: str | None = None,
        tasklist_id: str = "@default",
        parent: str | None = None,
    ) -> dict[str, Any]:
        """Create a task (a subtask when `parent` is a task ID). `due` is a day."""
        task = svc.tasks.create_task(
            title, notes=notes, due=parse_day(due), tasklist_id=tasklist_id, parent=parent
        )
        return to_json(task)  # type: ignore[no-any-return]

    @tool(WRITE)
    def tasks_complete(task_id: str, tasklist_id: str = "@default") -> dict[str, Any]:
        """Mark a task as completed."""
        return to_json(svc.tasks.complete_task(task_id, tasklist_id=tasklist_id))  # type: ignore[no-any-return]

    # --------------------------------------------------------- contacts

    @tool(READ)
    def contacts_search(query: str, max_results: int = 10) -> dict[str, Any]:
        """Contacts whose name, email, phone or company starts with `query`
        (max 30). Needs the Contacts scope."""
        return results(to_json(svc.contacts.search(query, max_results=max_results)))

    @tool(READ)
    def contacts_get(contact_id: str) -> dict[str, Any]:
        """One contact by ID ("c123" or "people/c123")."""
        contact = svc.contacts.get(contact_id)
        if contact is None:
            raise ToolError(f"No contact {contact_id}")
        return to_json(contact)  # type: ignore[no-any-return]

    return server


def main() -> None:
    """Console entry point: `gsuite-mcp` serves over stdio."""
    build_server().run("stdio")


if __name__ == "__main__":
    main()
