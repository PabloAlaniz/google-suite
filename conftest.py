"""Shared pytest fixtures for google-suite tests."""

import pytest
from unittest.mock import Mock, MagicMock


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
