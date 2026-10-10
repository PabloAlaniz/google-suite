"""The MCP server, through an in-memory MCP client, on mocked SDK clients."""

import json
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from mcp.client import Client

from gsuite_calendar import Event
from gsuite_contacts import Contact
from gsuite_core.exceptions import NotFoundError, PermissionDeniedError
from gsuite_drive import File, Permission
from gsuite_gmail import Message
from gsuite_mcp import Services, build_server
from gsuite_mcp.serialize import to_json
from gsuite_tasks import Task

DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"


@pytest.fixture
def auth():
    mock = MagicMock(name="auth")
    mock.is_authenticated.return_value = True
    mock.get_user_email.return_value = "me@example.com"
    mock.credentials.scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    return mock


@pytest.fixture
def services(auth):
    svc = Services(auth)
    for name in ("gmail", "calendar", "drive", "sheets", "tasks", "contacts"):
        svc.__dict__[name] = MagicMock(name=name)  # replaces the cached_property
    return svc


@pytest.fixture
def server(services):
    return build_server(services)


async def call(server, tool, /, **arguments):
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments)
    text = result.content[0].text if result.content else ""
    if result.is_error:
        return "error", text
    return "ok", json.loads(text)


def _message(**overrides):
    fields = {
        "id": "m1",
        "thread_id": "t1",
        "subject": "Invoice",
        "sender": "billing@example.com",
        "recipient": "me@example.com",
        "date": datetime(2026, 3, 1, 10, tzinfo=UTC),
        "snippet": "Your invoice",
        "plain": "Body text",
        "labels": ["INBOX"],
    }
    fields.update(overrides)
    return Message(**fields)


class TestTools:
    async def test_tools_are_annotated(self, server):
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}

        assert len(tools) == 23
        assert tools["gmail_search"].annotations.read_only_hint is True
        assert tools["gmail_send"].annotations.read_only_hint is False
        assert tools["gmail_send"].annotations.destructive_hint is False
        assert tools["calendar_delete_event"].annotations.destructive_hint is True
        assert tools["sheets_update"].annotations.destructive_hint is True
        assert all(t.description for t in tools.values())

    async def test_auth_status(self, server):
        status, body = await call(server, "auth_status")
        assert status == "ok"
        assert body["email"] == "me@example.com"


class TestAuthErrors:
    async def test_no_login_explains_how_to_log_in(self, auth):
        auth.is_authenticated.return_value = False
        auth.needs_refresh.return_value = False
        status, text = await call(build_server(Services(auth)), "gmail_search", query="x")
        assert status == "error"
        assert "gsuite auth login" in text

    async def test_expired_token_is_refreshed(self, auth, services, server):
        auth.is_authenticated.return_value = False
        auth.needs_refresh.return_value = True
        services.gmail.search.return_value = []
        assert await call(server, "auth_status") == (
            "ok",
            {"authenticated": True, "email": "me@example.com", "scopes": auth.credentials.scopes},
        )
        auth.refresh.assert_called_once()

    async def test_missing_scope_hint(self, services, server):
        services.tasks.list_tasks.side_effect = PermissionDeniedError("tasks", "list")
        status, text = await call(server, "tasks_list")
        assert status == "error"
        assert "--scopes default,tasks,contacts" in text

    async def test_other_sdk_errors(self, services, server):
        services.contacts.get.side_effect = NotFoundError("contacts", "contact", "c9")
        status, text = await call(server, "contacts_get", contact_id="c9")
        assert status == "error"
        assert "NotFoundError" in text


class TestGmail:
    async def test_search_returns_summaries(self, services, server):
        services.gmail.search.return_value = [_message()]

        status, body = await call(server, "gmail_search", query="is:unread", max_results=5)

        assert status == "ok"
        assert body["count"] == 1
        assert body["results"] == [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "Invoice",
                "sender": "billing@example.com",
                "date": "2026-03-01T10:00:00+00:00",
                "snippet": "Your invoice",
                "labels": ["INBOX"],
                "attachments": [],
            }
        ]
        services.gmail.search.assert_called_once_with("is:unread", max_results=5)

    async def test_read(self, services, server):
        services.gmail.get_message.return_value = _message()
        status, body = await call(server, "gmail_read", message_id="m1")
        assert body["body"] == "Body text"

    async def test_read_missing(self, services, server):
        services.gmail.get_message.return_value = None
        assert (await call(server, "gmail_read", message_id="x"))[0] == "error"

    async def test_send_and_reply(self, services, server):
        services.gmail.send.return_value = _message(id="s1")
        services.gmail.get_message.return_value = _message()
        services.gmail.reply.return_value = _message(id="r1")

        assert (await call(server, "gmail_send", to=["a@b.c"], subject="Hi", body="x"))[1] == {
            "id": "s1",
            "thread_id": "t1",
        }
        assert services.gmail.send.call_args.kwargs["to"] == ["a@b.c"]
        await call(server, "gmail_reply", message_id="m1", body="Thanks", reply_all=True)
        services.gmail.reply.assert_called_once_with(
            services.gmail.get_message.return_value, "Thanks", reply_all=True
        )

    async def test_draft(self, services, server):
        services.gmail.create_draft.return_value = MagicMock(id="d1")
        status, body = await call(server, "gmail_create_draft", to=["a@b.c"], subject="S", body="B")
        assert body == {"draft_id": "d1"}


class TestCalendar:
    async def test_list(self, services, server):
        services.calendar.get_upcoming.return_value = [
            Event(id="e1", summary="Sync", start=datetime(2026, 3, 2, 10, tzinfo=UTC))
        ]
        status, body = await call(server, "calendar_list_events", days=2)
        (event,) = body["results"]
        assert event["summary"] == "Sync"
        assert event["start"] == "2026-03-02T10:00:00+00:00"
        assert "raw" not in event

    async def test_create_timed_and_all_day(self, services, server):
        services.calendar.create_event.return_value = Event(id="e1", summary="x")

        await call(
            server,
            "calendar_create_event",
            summary="Sync",
            start="2026-03-02T10:00",
            meet=True,
            send_updates="all",
        )
        kwargs = services.calendar.create_event.call_args.kwargs
        assert kwargs["start"] == datetime(2026, 3, 2, 10)
        assert kwargs["all_day"] is False
        assert (kwargs["meet"], kwargs["send_updates"]) == (True, "all")

        await call(server, "calendar_create_event", summary="Holiday", start="2026-03-24")
        kwargs = services.calendar.create_event.call_args.kwargs
        assert kwargs["start"] == date(2026, 3, 24)
        assert kwargs["all_day"] is True

    async def test_bad_date(self, server):
        status, text = await call(server, "calendar_create_event", summary="x", start="tomorrow")
        assert status == "error"
        assert "ISO" in text

    async def test_delete_missing(self, services, server):
        services.calendar.delete_event.return_value = False
        assert (await call(server, "calendar_delete_event", event_id="e9"))[0] == "error"

    async def test_free_busy_needs_times(self, services, server):
        status, _ = await call(
            server, "calendar_free_busy", time_min="2026-03-02", time_max="2026-03-03"
        )
        assert status == "error"
        services.calendar.get_free_busy.return_value = {"primary": []}
        status, body = await call(
            server, "calendar_free_busy", time_min="2026-03-02T09:00", time_max="2026-03-02T18:00"
        )
        assert body == {"primary": []}


class TestDrive:
    async def test_search_by_name_or_query(self, services, server):
        services.drive.search.return_value = [
            File(id="f1", name="a.pdf", mime_type="application/pdf")
        ]
        status, body = await call(server, "drive_search", name="a")
        assert body["results"][0]["id"] == "f1"
        services.drive.list_files.return_value = []
        await call(server, "drive_search", query="trashed = false", max_results=5)
        services.drive.list_files.assert_called_once_with(query="trashed = false", max_results=5)

    @pytest.mark.parametrize(
        ("mime", "export"),
        [(DOC, "txt"), (SHEET, "csv"), ("application/vnd.google-apps.presentation", "txt")],
    )
    async def test_read_google_files_as_text(self, services, server, mime, export):
        services.drive.get.return_value = File(id="f1", name="Doc", mime_type=mime)
        services.drive.export.return_value = b"hello"
        status, body = await call(server, "drive_read_file", file_id="f1")
        assert body["text"] == "hello"
        services.drive.export.assert_called_once_with("f1", export)

    async def test_read_text_file_and_truncate(self, services, server):
        services.drive.get.return_value = File(id="f1", name="a.txt", mime_type="text/plain")
        services.drive.get_content.return_value = b"0123456789"
        status, body = await call(server, "drive_read_file", file_id="f1", max_chars=4)
        assert (body["text"], body["truncated"]) == ("0123", True)

    async def test_binary_refused(self, services, server):
        services.drive.get.return_value = File(id="f1", name="a.pdf", mime_type="application/pdf")
        status, text = await call(server, "drive_read_file", file_id="f1")
        assert status == "error"
        assert "gsuite drive download f1" in text

    async def test_share(self, services, server):
        assert (await call(server, "drive_share", file_id="f1"))[0] == "error"
        services.drive.add_permission.return_value = Permission(
            id="p1", type="anyone", role="reader"
        )
        status, body = await call(server, "drive_share", file_id="f1", anyone=True)
        assert body["type"] == "anyone"
        assert services.drive.add_permission.call_args.kwargs["type"] == "anyone"


class TestSheets:
    @pytest.mark.parametrize(
        ("spreadsheet", "method"),
        [
            ("https://docs.google.com/spreadsheets/d/abc/edit", "open_by_url"),
            ("1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "open_by_key"),
            ("Budget", "open"),
        ],
    )
    async def test_resolves_url_id_or_title(self, services, server, spreadsheet, method):
        ws = getattr(services.sheets, method).return_value.sheet1
        ws.title = "Data"
        ws.get.return_value = [["a", "b"]]

        status, body = await call(server, "sheets_read", spreadsheet=spreadsheet, range="A1:B1")

        assert body == {"sheet": "Data", "range": "A1:B1", "values": [["a", "b"]]}

    async def test_missing_tab(self, services, server):
        services.sheets.open.return_value.worksheet.return_value = None
        status, text = await call(server, "sheets_read", spreadsheet="Budget", sheet="Nope")
        assert status == "error"

    async def test_title_not_found(self, services, server):
        services.sheets.open.side_effect = ValueError("Spreadsheet not found: Budget")
        status, text = await call(server, "sheets_read", spreadsheet="Budget")
        assert (status, text.endswith("Spreadsheet not found: Budget")) == ("error", True)

    async def test_writes(self, services, server):
        ws = services.sheets.open.return_value.sheet1
        ws.title = "Data"
        ws.upsert.return_value = {"updated": 1, "appended": 0}

        assert (await call(server, "sheets_append", spreadsheet="B", rows=[["x", 1]]))[1][
            "appended"
        ] == 1
        ws.append_rows.assert_called_once_with([["x", 1]])
        await call(server, "sheets_update", spreadsheet="B", range="B2", values=[[5]])
        ws.update.assert_called_once_with("B2", [[5]])
        status, body = await call(
            server, "sheets_upsert", spreadsheet="B", rows=[{"name": "Ana"}], key="name"
        )
        assert body == {"updated": 1, "appended": 0}


class TestTasksAndContacts:
    async def test_tasks(self, services, server):
        services.tasks.list_tasks.return_value = [
            Task(id="t1", title="Pay", tasklist_id="@default", due=date(2026, 3, 1))
        ]
        status, body = await call(server, "tasks_list", due_before="2026-03-31")
        assert body["results"][0]["due"] == "2026-03-01"
        assert services.tasks.list_tasks.call_args.kwargs["due_max"] == date(2026, 3, 31)

        services.tasks.create_task.return_value = Task(id="t2", title="New", tasklist_id="@default")
        await call(server, "tasks_add", title="New", due="2026-04-01T09:00")
        assert services.tasks.create_task.call_args.kwargs["due"] == date(2026, 4, 1)

        services.tasks.complete_task.return_value = Task(
            id="t2", title="New", tasklist_id="@default", status="completed"
        )
        assert (await call(server, "tasks_complete", task_id="t2"))[1]["status"] == "completed"

    async def test_contacts(self, services, server):
        services.contacts.search.return_value = [
            Contact(resource_name="people/c1", display_name="Ana", emails=["a@x.com"])
        ]
        status, body = await call(server, "contacts_search", query="ana")
        assert body["results"][0]["emails"] == ["a@x.com"]
        services.contacts.get.return_value = None
        assert (await call(server, "contacts_get", contact_id="c9"))[0] == "error"


def test_to_json_skips_raw_and_private_fields():
    message = _message()
    data = to_json(message)
    assert "raw" not in data and "_gmail" not in data and "plain" not in data
    assert data["date"] == "2026-03-01T10:00:00+00:00"
