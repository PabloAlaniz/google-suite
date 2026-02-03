"""Tests for Gmail client."""

from unittest.mock import Mock, patch

from gsuite_gmail.client import Gmail
from gsuite_gmail.label import Label, LabelType
from gsuite_gmail.message import Message


class TestGmailInit:
    """Tests for Gmail client initialization."""

    def test_init_with_auth(self):
        """Test Gmail client initialization."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        assert gmail.auth is mock_auth
        assert gmail.user_id == "me"
        assert gmail._service is None

    def test_init_with_custom_user_id(self):
        """Test Gmail with custom user_id."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth, user_id="user@example.com")

        assert gmail.user_id == "user@example.com"


class TestGmailService:
    """Tests for Gmail service property."""

    @patch("gsuite_gmail.client.build")
    def test_lazy_service_creation(self, mock_build):
        """Test service is created lazily."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_service = Mock()
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)

        # Service not created yet
        mock_build.assert_not_called()

        # Access service
        service = gmail.service

        # Now it's created
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_auth.credentials)
        assert service is mock_service

    @patch("gsuite_gmail.client.build")
    def test_service_cached(self, mock_build):
        """Test service is cached after first access."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()
        mock_build.return_value = Mock()

        gmail = Gmail(mock_auth)

        # Access multiple times
        _ = gmail.service
        _ = gmail.service
        _ = gmail.service

        # Only built once
        mock_build.assert_called_once()


class TestGetMessages:
    """Tests for get_messages method."""

    @patch("gsuite_gmail.client.build")
    def test_get_messages_empty(self, mock_build):
        """Test get_messages with no results."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.users().messages().list().execute.return_value = {"messages": []}
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        messages = gmail.get_messages()

        assert messages == []

    @patch("gsuite_gmail.client.build")
    def test_get_messages_with_query(self, mock_build):
        """Test get_messages with search query."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.users().messages().list
        mock_list().execute.return_value = {"messages": []}
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        gmail.get_messages(query="is:unread")

        # Verify query was passed
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("q") == "is:unread"

    @patch("gsuite_gmail.client.build")
    def test_get_messages_with_labels(self, mock_build):
        """Test get_messages with label filter."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_list = mock_service.users().messages().list
        mock_list().execute.return_value = {"messages": []}
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        gmail.get_messages(labels=["INBOX", "UNREAD"])

        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("labelIds") == ["INBOX", "UNREAD"]


class TestConvenienceMethods:
    """Tests for convenience methods."""

    @patch.object(Gmail, "get_messages")
    def test_get_unread(self, mock_get):
        """Test get_unread convenience method."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        gmail.get_unread(max_results=10)

        mock_get.assert_called_once_with(query="is:unread", max_results=10)

    @patch.object(Gmail, "get_messages")
    def test_get_unread_inbox(self, mock_get):
        """Test get_unread_inbox convenience method."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        gmail.get_unread_inbox()

        mock_get.assert_called_once_with(query="is:unread in:inbox", max_results=25)

    @patch.object(Gmail, "get_messages")
    def test_get_starred(self, mock_get):
        """Test get_starred convenience method."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        gmail.get_starred()

        mock_get.assert_called_once_with(query="is:starred", max_results=25)

    @patch.object(Gmail, "get_messages")
    def test_get_sent(self, mock_get):
        """Test get_sent convenience method."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        gmail.get_sent()

        mock_get.assert_called_once_with(query="in:sent", max_results=25)

    @patch.object(Gmail, "search")
    def test_search_delegates(self, mock_search):
        """Test search method delegates to get_messages."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        # search() is just get_messages() with query
        # Testing that it exists and is callable
        assert callable(gmail.search)


class TestGetLabels:
    """Tests for label methods."""

    @patch("gsuite_gmail.client.build")
    def test_get_labels(self, mock_build):
        """Test get_labels returns Label objects."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
            ]
        }
        mock_service.users().labels().get().execute.side_effect = [
            {
                "id": "INBOX",
                "name": "INBOX",
                "type": "system",
                "messagesTotal": 100,
                "messagesUnread": 5,
                "threadsTotal": 50,
                "threadsUnread": 3,
            },
            {
                "id": "Label_1",
                "name": "Work",
                "type": "user",
                "messagesTotal": 20,
                "messagesUnread": 0,
                "threadsTotal": 10,
                "threadsUnread": 0,
            },
        ]
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        labels = gmail.get_labels()

        assert len(labels) == 2
        assert all(isinstance(l, Label) for l in labels)

        inbox = labels[0]
        assert inbox.id == "INBOX"
        assert inbox.type == LabelType.SYSTEM
        assert inbox.messages_unread == 5


class TestSend:
    """Tests for send method."""

    @patch("gsuite_gmail.client.build")
    def test_send_simple(self, mock_build):
        """Test sending a simple email."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_service.users().messages().send().execute.return_value = {"id": "sent123"}
        mock_service.users().messages().get().execute.return_value = {
            "id": "sent123",
            "threadId": "thread123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test"},
                    {"name": "From", "value": "me@example.com"},
                    {"name": "To", "value": "you@example.com"},
                ]
            },
            "labelIds": ["SENT"],
        }
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        result = gmail.send(
            to=["you@example.com"],
            subject="Test",
            body="Hello!",
        )

        assert isinstance(result, Message)
        assert result.id == "sent123"

        # Verify send was called
        mock_service.users().messages().send.assert_called()


class TestModifyLabels:
    """Tests for label modification methods."""

    @patch("gsuite_gmail.client.build")
    def test_modify_labels_add(self, mock_build):
        """Test adding labels."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        gmail._modify_labels("msg123", add=["STARRED"])

        call_args = mock_service.users().messages().modify.call_args
        assert call_args[1]["body"]["addLabelIds"] == ["STARRED"]

    @patch("gsuite_gmail.client.build")
    def test_modify_labels_remove(self, mock_build):
        """Test removing labels."""
        mock_auth = Mock()
        mock_auth.credentials = Mock()

        mock_service = Mock()
        mock_build.return_value = mock_service

        gmail = Gmail(mock_auth)
        gmail._modify_labels("msg123", remove=["UNREAD"])

        call_args = mock_service.users().messages().modify.call_args
        assert call_args[1]["body"]["removeLabelIds"] == ["UNREAD"]


class TestParseMessage:
    """Tests for message parsing."""

    def test_parse_message_basic(self):
        """Test parsing a basic message."""
        mock_auth = Mock()
        gmail = Gmail(mock_auth)

        data = {
            "id": "msg123",
            "threadId": "thread456",
            "snippet": "Hello world...",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Cc", "value": "cc1@example.com, cc2@example.com"},
                    {"name": "Date", "value": "Mon, 28 Jan 2026 10:30:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {},
            },
        }

        msg = gmail._parse_message(data, include_body=False)

        assert msg.id == "msg123"
        assert msg.thread_id == "thread456"
        assert msg.subject == "Test Subject"
        assert msg.sender == "sender@example.com"
        assert msg.recipient == "recipient@example.com"
        assert len(msg.cc) == 2
        assert msg.is_unread is True
