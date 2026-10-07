"""End-to-end flows against the real Google APIs (see conftest.py to enable them).

Each test leaves the account as it found it: whatever it creates is deleted in
a ``finally`` block, even when an assertion fails.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from gsuite_calendar import Calendar
from gsuite_contacts import Contacts
from gsuite_core import Scopes
from gsuite_drive import Drive
from gsuite_gmail import Gmail
from gsuite_sheets import Sheets
from gsuite_tasks import Tasks


def test_gmail_profile_and_labels(auth):
    gmail = Gmail(auth)

    profile = gmail.get_profile()
    labels = {label.id for label in gmail.get_labels()}

    assert "@" in profile["emailAddress"]
    assert {"INBOX", "SENT"} <= labels


def test_calendar_event_roundtrip(auth, name):
    calendar = Calendar(auth)
    # Far in the future so it never shows up in anyone's agenda
    start = datetime(2099, 1, 1, 10, tzinfo=UTC)
    event = calendar.create_event(name, start=start, end=start + timedelta(hours=1))
    try:
        fetched = calendar.get_event(event.id)
        assert fetched is not None
        assert fetched.summary == name
        assert fetched.start is not None
        assert fetched.start.astimezone(UTC) == start
    finally:
        assert calendar.delete_event(event.id)


def test_drive_upload_download_delete(auth, name):
    drive = Drive(auth)
    file = drive.upload_content(b"hello, drive", f"{name}.txt", mime_type="text/plain")
    try:
        assert drive.get_content(file.id) == b"hello, drive"
        assert drive.get(file.id).name == f"{name}.txt"
    finally:
        assert drive.delete(file.id)
    assert drive.get(file.id) is None


def test_sheets_write_read_upsert(auth, name):
    sheets = Sheets(auth)
    spreadsheet = sheets.create(name)
    try:
        ws = spreadsheet.sheet1
        assert ws is not None
        ws.update("A1", [["sku", "qty"], ["a", 1], ["b", 2]])

        result = ws.upsert([{"sku": "b", "qty": 5}, {"sku": "c", "qty": 7}], key="sku")

        assert result == {"updated": 1, "appended": 1}
        records = ws.get_all_records()
        assert {r["sku"]: r["qty"] for r in records} == {"a": 1, "b": 5, "c": 7}
        # Sheet titles with spaces and quotes need quoting in A1 ranges
        odd = spreadsheet.add_worksheet("Pablo's data")
        odd.update("A1", [["x"]])
        assert odd.get_all_values() == [["x"]]
    finally:
        sheets.delete(spreadsheet.id)


async def test_async_sheets_roundtrip(auth, name):
    from gsuite_sheets.aio import AsyncSheets

    async with AsyncSheets(auth) as sheets:
        spreadsheet = await sheets.create(name)
        try:
            ws = spreadsheet.worksheets()[0]
            await ws.append_rows([["name"], ["ana"], ["bob"]])
            assert [r["name"] for r in await ws.get_all_records()] == ["ana", "bob"]
        finally:
            await sheets.delete(spreadsheet.id)


def test_tasks_roundtrip(auth, need_scopes, name):
    need_scopes(Scopes.tasks(), "Tasks")
    tasks = Tasks(auth)
    tasklist = tasks.create_tasklist(name)
    try:
        parent = tasks.create_task("parent", due=date(2099, 1, 1), tasklist_id=tasklist.id)
        child = tasks.create_task("child", parent=parent.id, tasklist_id=tasklist.id)
        assert child.parent == parent.id
        assert parent.due == date(2099, 1, 1)

        assert tasks.complete_task(parent.id, tasklist_id=tasklist.id).is_completed
        pending = tasks.list_tasks(tasklist.id, show_completed=False)
        assert [t.title for t in pending] == ["child"]

        reopened = tasks.reopen_task(parent.id, tasklist_id=tasklist.id)
        assert not reopened.is_completed
        assert reopened.completed is None
    finally:
        assert tasks.delete_tasklist(tasklist.id)
    assert tasks.get_tasklist(tasklist.id) is None


def test_contacts_roundtrip(auth, need_scopes, name):
    need_scopes(Scopes.contacts(), "Contacts")
    contacts = Contacts(auth)
    contact = contacts.create(given_name=name, family_name="Test", emails=[f"{name}@example.com"])
    try:
        assert contacts.get(contact.id).email == f"{name}@example.com"

        updated = contacts.update(contact.id, given_name=f"{name}-2", phones=["+54 11 5555-0000"])

        assert updated.given_name == f"{name}-2"
        assert updated.family_name == "Test"  # kept
        assert updated.phones == ["+54 11 5555-0000"]
    finally:
        assert contacts.delete(contact.id)
    assert contacts.get(contact.id) is None


@pytest.mark.parametrize("missing", ["nonexistent-id-0000"])
def test_not_found_contracts(auth, missing):
    """Missing resources give None/False, not exceptions."""
    assert Calendar(auth).get_event(missing) is None
    assert Drive(auth).get(missing) is None
