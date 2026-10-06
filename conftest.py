"""Shared pytest fixtures for google-suite tests."""

from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest


def pytest_collection_finish(session):
    """Fail if two test modules share a basename.

    Every tests/ dir is a package named ``tests``; with --import-mode=importlib
    same-named modules collapse into one and the others silently never run.
    """
    paths = defaultdict(set)
    for item in session.items:
        path = Path(item.path)
        paths[path.name].add(path)
    duplicates = {name: sorted(map(str, ps)) for name, ps in paths.items() if len(ps) > 1}
    if duplicates:
        raise pytest.UsageError(f"Duplicate test module names (rename them): {duplicates}")


@pytest.fixture
def mock_credentials():
    """Create mock Google credentials."""
    creds = Mock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "mock_refresh_token"
    creds.token = "mock_access_token"
    creds.scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    return creds


@pytest.fixture
def mock_auth(mock_credentials):
    """Create mock GoogleAuth instance."""
    auth = Mock()
    auth.credentials = mock_credentials
    auth.is_authenticated.return_value = True
    auth.needs_refresh.return_value = False
    return auth


@pytest.fixture
def mock_google_service():
    """Create a generic mock Google API service."""
    return MagicMock()


# Gmail fixtures
@pytest.fixture
def sample_gmail_message():
    """Sample Gmail message data from API."""
    return {
        "id": "msg_123",
        "threadId": "thread_456",
        "snippet": "Hello, this is a test message...",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Mon, 28 Jan 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQ="},  # "Hello World" base64
        },
    }


# Calendar fixtures
@pytest.fixture
def sample_calendar_event():
    """Sample Calendar event data from API."""
    return {
        "id": "event_123",
        "summary": "Team Meeting",
        "description": "Weekly sync",
        "location": "Conference Room A",
        "start": {"dateTime": "2026-01-28T10:00:00Z"},
        "end": {"dateTime": "2026-01-28T11:00:00Z"},
        "status": "confirmed",
        "htmlLink": "https://calendar.google.com/event?id=123",
    }


@pytest.fixture
def sample_all_day_event():
    """Sample all-day Calendar event."""
    return {
        "id": "event_456",
        "summary": "Holiday",
        "start": {"date": "2026-01-28"},
        "end": {"date": "2026-01-29"},
    }


# Drive fixtures
@pytest.fixture
def sample_drive_file():
    """Sample Drive file data from API."""
    return {
        "id": "file_123",
        "name": "document.pdf",
        "mimeType": "application/pdf",
        "size": "1024",
        "createdTime": "2026-01-28T10:00:00.000Z",
        "modifiedTime": "2026-01-28T11:00:00.000Z",
        "webViewLink": "https://drive.google.com/file/d/123/view",
    }


@pytest.fixture
def sample_drive_folder():
    """Sample Drive folder data from API."""
    return {
        "id": "folder_123",
        "name": "My Folder",
        "mimeType": "application/vnd.google-apps.folder",
        "createdTime": "2026-01-28T10:00:00.000Z",
    }


# Sheets fixtures
@pytest.fixture
def sample_spreadsheet():
    """Sample Sheets spreadsheet data from API."""
    return {
        "spreadsheetId": "sheet_123",
        "properties": {
            "title": "My Spreadsheet",
            "locale": "en_US",
            "timeZone": "America/Buenos_Aires",
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Sheet1",
                    "index": 0,
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": 26,
                    },
                },
            },
        ],
    }


@pytest.fixture
def http_error():
    """Factory for real googleapiclient HttpErrors: http_error(404, reason=...)."""
    import json

    import httplib2
    from googleapiclient.errors import HttpError

    def _make(status: int, reason: str | None = None) -> HttpError:
        body = {"error": {"code": status, "message": "error"}}
        if reason:
            body["error"]["errors"] = [{"reason": reason}]
        return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode())

    return _make


class _FakeBatch:
    """BatchHttpRequest stand-in: runs each request's execute() and reports it."""

    def __init__(self, callback):
        self.callback = callback
        self.items = []

    def add(self, request, request_id):
        self.items.append((request, request_id))

    def execute(self):
        for request, request_id in self.items:
            try:
                response = request.execute()
            except Exception as exc:  # delivered to the callback, like the real batch
                self.callback(request_id, None, exc)
            else:
                self.callback(request_id, response, None)


@pytest.fixture
def batching():
    """Make a mocked service's HTTP batches run their requests: batching(service)."""

    def enable(service):
        service.new_batch_http_request.side_effect = lambda callback: _FakeBatch(callback)
        return service

    return enable


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "memory_only: engine test that only makes sense against the in-memory backend"
    )


def pytest_addoption(parser):
    parser.addoption(
        "--engine-backend",
        choices=["memory", "adapter"],
        default="memory",
        help=(
            "Run the Sheets engine tests against the in-memory backend directly, or "
            "through gsuite_sheets.engine_adapter over a fake googleapiclient service"
        ),
    )


@pytest.fixture(autouse=True)
def _engine_backend(request, monkeypatch):
    """With --engine-backend=adapter, InMemoryBackend.manager() goes through the adapter.

    Same tests, same in-memory state, but every engine call is translated to
    googleapiclient requests by the real adapter first: a behavioral contract test.
    """
    if request.config.getoption("--engine-backend") != "adapter":
        return
    if "test_engine_" not in request.node.nodeid:
        return
    if request.node.get_closest_marker("memory_only"):
        pytest.skip("inspects the in-memory emulator itself")

    from gsuite_sheets.engine.facade import SheetManager
    from gsuite_sheets.engine.testing import InMemoryBackend
    from gsuite_sheets.engine.testing.google_api_fake import adapter_client

    def manager(self, doc_name=None, *, key=None, **kwargs):
        return SheetManager(doc_name, key=key, sheets_client=adapter_client(self.client), **kwargs)

    monkeypatch.setattr(InMemoryBackend, "manager", manager)
