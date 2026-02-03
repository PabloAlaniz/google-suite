"""Tests for Gmail Message entity."""

from datetime import datetime

import pytest

from gsuite_gmail.message import Attachment, Message


class TestMessage:
    """Tests for Message entity."""

    @pytest.fixture
    def sample_message(self):
        """Create a sample message."""
        return Message(
            id="msg123",
            thread_id="thread456",
            subject="Test Subject",
            sender="sender@example.com",
            recipient="recipient@example.com",
            cc=["cc@example.com"],
            date=datetime(2026, 1, 28, 10, 30, 0),
            snippet="This is a test...",
            plain="This is the plain text body.",
            html="<p>This is the HTML body.</p>",
            labels=["INBOX", "UNREAD", "STARRED"],
            attachments=[],
        )

    def test_is_unread_true(self, sample_message):
        """Test is_unread when UNREAD label is present."""
        assert sample_message.is_unread is True

    def test_is_unread_false(self, sample_message):
        """Test is_unread when UNREAD label is absent."""
        sample_message.labels = ["INBOX"]
        assert sample_message.is_unread is False

    def test_is_starred_true(self, sample_message):
        """Test is_starred when STARRED label is present."""
        assert sample_message.is_starred is True

    def test_is_starred_false(self, sample_message):
        """Test is_starred when STARRED label is absent."""
        sample_message.labels = ["INBOX"]
        assert sample_message.is_starred is False

    def test_is_important(self, sample_message):
        """Test is_important property."""
        assert sample_message.is_important is False

        sample_message.labels.append("IMPORTANT")
        assert sample_message.is_important is True

    def test_body_prefers_plain(self, sample_message):
        """Test body property prefers plain text."""
        assert sample_message.body == "This is the plain text body."

    def test_body_fallback_to_html(self):
        """Test body falls back to HTML when no plain text."""
        message = Message(
            id="1",
            thread_id="1",
            subject="",
            sender="",
            recipient="",
            html="<p>HTML only</p>",
        )
        assert message.body == "<p>HTML only</p>"

    def test_body_empty(self):
        """Test body returns empty string when no content."""
        message = Message(
            id="1",
            thread_id="1",
            subject="",
            sender="",
            recipient="",
        )
        assert message.body == ""


class TestAttachment:
    """Tests for Attachment entity."""

    def test_attachment_creation(self):
        """Test creating an attachment."""
        att = Attachment(
            id="att123",
            filename="document.pdf",
            mime_type="application/pdf",
            size=1024,
        )

        assert att.id == "att123"
        assert att.filename == "document.pdf"
        assert att.mime_type == "application/pdf"
        assert att.size == 1024

    def test_download_without_client(self):
        """Test download raises error without Gmail client."""
        att = Attachment(
            id="att123",
            filename="document.pdf",
            mime_type="application/pdf",
            size=1024,
        )

        with pytest.raises(RuntimeError, match="not linked"):
            att.download()
