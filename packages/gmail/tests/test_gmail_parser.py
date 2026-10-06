"""Tests for Gmail parser."""

import pytest

from gsuite_gmail.label import LabelType
from gsuite_gmail.parser import GmailParser


class TestGmailParser:
    """Tests for GmailParser."""

    def test_parse_message_basic(self):
        """Test parsing a basic message."""
        data = {
            "id": "msg123",
            "threadId": "thread456",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "Hello there...",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Cc", "value": "cc1@example.com, cc2@example.com"},
                    {"name": "Date", "value": "Mon, 3 Feb 2026 10:00:00 +0000"},
                ],
            },
        }

        msg = GmailParser.parse_message(data, include_body=False)

        assert msg.id == "msg123"
        assert msg.thread_id == "thread456"
        assert msg.subject == "Test Subject"
        assert msg.sender == "sender@example.com"
        assert msg.recipient == "recipient@example.com"
        assert msg.cc == ["cc1@example.com", "cc2@example.com"]
        assert "INBOX" in msg.labels
        assert "UNREAD" in msg.labels

    def test_parse_message_with_plain_body(self):
        """Test parsing message with plain text body."""
        import base64

        body_content = "Hello, this is the message body."
        encoded_body = base64.urlsafe_b64encode(body_content.encode()).decode()

        data = {
            "id": "msg123",
            "threadId": "thread123",
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Subject", "value": "Test"}],
                "body": {"data": encoded_body},
            },
        }

        msg = GmailParser.parse_message(data, include_body=True)

        assert msg.plain == body_content
        assert msg.html is None

    def test_parse_message_with_html_body(self):
        """Test parsing message with HTML body."""
        import base64

        html_content = "<html><body><h1>Hello</h1></body></html>"
        encoded_body = base64.urlsafe_b64encode(html_content.encode()).decode()

        data = {
            "id": "msg123",
            "threadId": "thread123",
            "payload": {
                "mimeType": "text/html",
                "headers": [{"name": "Subject", "value": "Test"}],
                "body": {"data": encoded_body},
            },
        }

        msg = GmailParser.parse_message(data, include_body=True)

        assert msg.plain is None
        assert msg.html == html_content

    def test_parse_message_multipart(self):
        """Test parsing multipart message with both plain and HTML."""
        import base64

        plain = "Plain text version"
        html = "<p>HTML version</p>"

        data = {
            "id": "msg123",
            "threadId": "thread123",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [{"name": "Subject", "value": "Test"}],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": base64.urlsafe_b64encode(plain.encode()).decode()},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(html.encode()).decode()},
                    },
                ],
            },
        }

        msg = GmailParser.parse_message(data, include_body=True)

        assert msg.plain == plain
        assert msg.html == html

    def test_parse_message_with_attachment(self):
        """Test parsing message with attachment."""
        data = {
            "id": "msg123",
            "threadId": "thread123",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [{"name": "Subject", "value": "With Attachment"}],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "SGVsbG8="},  # "Hello" base64
                    },
                    {
                        "filename": "document.pdf",
                        "mimeType": "application/pdf",
                        "body": {
                            "attachmentId": "att123",
                            "size": 12345,
                        },
                    },
                ],
            },
        }

        msg = GmailParser.parse_message(data, include_body=True)

        assert len(msg.attachments) == 1
        assert msg.attachments[0].filename == "document.pdf"
        assert msg.attachments[0].mime_type == "application/pdf"
        assert msg.attachments[0].size == 12345
        assert msg.attachments[0].id == "att123"

    def test_parse_message_internal_date_fallback(self):
        """Test date parsing falls back to internalDate."""
        data = {
            "id": "msg123",
            "threadId": "thread123",
            "internalDate": "1706958000000",  # 2026-02-03 10:00:00 UTC
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test"},
                    {"name": "Date", "value": "invalid date"},
                ],
            },
        }

        msg = GmailParser.parse_message(data, include_body=False)

        assert msg.date is not None

    def test_parse_label_user(self):
        """Test parsing a user label."""
        data = {
            "id": "Label_123",
            "name": "My Custom Label",
            "type": "user",
            "messagesTotal": 42,
            "messagesUnread": 5,
            "threadsTotal": 30,
            "threadsUnread": 3,
        }

        label = GmailParser.parse_label(data)

        assert label.id == "Label_123"
        assert label.name == "My Custom Label"
        assert label.type == LabelType.USER
        assert label.messages_total == 42
        assert label.messages_unread == 5

    def test_parse_label_system(self):
        """Test parsing a system label."""
        data = {
            "id": "INBOX",
            "name": "INBOX",
            "type": "system",
            "messagesTotal": 100,
            "messagesUnread": 10,
        }

        label = GmailParser.parse_label(data)

        assert label.id == "INBOX"
        assert label.type == LabelType.SYSTEM
