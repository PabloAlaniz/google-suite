"""Gmail client - high-level interface."""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gsuite_core import GoogleAuth, api_call, api_call_optional
from gsuite_gmail.label import Label
from gsuite_gmail.message import Message
from gsuite_gmail.parser import GmailParser
from gsuite_gmail.query import Query
from gsuite_gmail.thread import Thread

logger = logging.getLogger(__name__)


class Gmail:
    """
    High-level Gmail client.

    Example:
        auth = GoogleAuth()
        auth.authenticate()

        gmail = Gmail(auth)

        # Get unread
        for msg in gmail.get_unread():
            print(msg.subject)
            msg.mark_as_read()

        # Send
        gmail.send(
            to=["user@example.com"],
            subject="Hello",
            body="World",
        )
    """

    def __init__(self, auth: GoogleAuth, user_id: str = "me"):
        """
        Initialize Gmail client.

        Args:
            auth: GoogleAuth instance with valid credentials
            user_id: Gmail user ID ("me" for authenticated user)
        """
        self.auth = auth
        self.user_id = user_id
        self._service = None
        self._labels_cache: dict[str, str] | None = None

    @property
    def service(self):
        """Lazy-load Gmail API service."""
        if self._service is None:
            self._service = build("gmail", "v1", credentials=self.auth.credentials)
        return self._service

    # ========== Message retrieval ==========

    def get_messages(
        self,
        query: str | Query | None = None,
        labels: list[str] | None = None,
        max_results: int = 25,
        include_body: bool = True,
    ) -> list[Message]:
        """
        Get messages matching criteria.

        Args:
            query: Gmail search query (str or Query object)
            labels: Filter by label IDs
            max_results: Maximum messages to return
            include_body: Whether to fetch full message content

        Returns:
            List of Message objects
        """
        request_params = {
            "userId": self.user_id,
            "maxResults": min(max_results, 500),
        }

        if query:
            request_params["q"] = str(query)
        if labels:
            request_params["labelIds"] = labels

        response = self.service.users().messages().list(**request_params).execute()

        messages = []
        for msg_ref in response.get("messages", []):
            msg = self._get_message_by_id(msg_ref["id"], include_body)
            messages.append(msg)

        return messages

    def search(
        self,
        query: str | Query,
        max_results: int = 25,
    ) -> list[Message]:
        """
        Search messages with a query.

        Args:
            query: Gmail search query
            max_results: Maximum results

        Returns:
            List of matching messages
        """
        return self.get_messages(query=query, max_results=max_results)

    def get_unread(self, max_results: int = 25) -> list[Message]:
        """Get unread messages."""
        return self.get_messages(query="is:unread", max_results=max_results)

    def get_unread_inbox(self, max_results: int = 25) -> list[Message]:
        """Get unread messages in inbox."""
        return self.get_messages(query="is:unread in:inbox", max_results=max_results)

    def get_starred(self, max_results: int = 25) -> list[Message]:
        """Get starred messages."""
        return self.get_messages(query="is:starred", max_results=max_results)

    def get_important(self, max_results: int = 25) -> list[Message]:
        """Get important messages."""
        return self.get_messages(query="is:important", max_results=max_results)

    def get_sent(self, max_results: int = 25) -> list[Message]:
        """Get sent messages."""
        return self.get_messages(query="in:sent", max_results=max_results)

    def get_drafts(self, max_results: int = 25) -> list[Message]:
        """Get draft messages."""
        return self.get_messages(query="in:drafts", max_results=max_results)

    def get_message(self, message_id: str) -> Message | None:
        """Get a specific message by ID."""
        return self._get_message_by_id(message_id, include_body=True)

    def _get_message_by_id(self, message_id: str, include_body: bool = True) -> Message:
        """Internal: fetch and parse a message."""
        msg_data = (
            self.service.users()
            .messages()
            .get(
                userId=self.user_id,
                id=message_id,
                format="full" if include_body else "metadata",
            )
            .execute()
        )

        return self._parse_message(msg_data, include_body)

    # ========== Threads ==========

    def get_thread(self, thread_id: str) -> Thread:
        """Get a full thread by ID."""
        thread_data = (
            self.service.users()
            .threads()
            .get(
                userId=self.user_id,
                id=thread_id,
                format="full",
            )
            .execute()
        )

        messages = [
            self._parse_message(msg_data, include_body=True)
            for msg_data in thread_data.get("messages", [])
        ]

        return Thread(
            id=thread_data["id"],
            messages=messages,
            snippet=thread_data.get("snippet", ""),
        )

    # ========== Labels ==========

    def get_labels(self) -> list[Label]:
        """Get all labels."""
        response = self.service.users().labels().list(userId=self.user_id).execute()

        labels = []
        for label_data in response.get("labels", []):
            # Fetch full details
            full_label = (
                self.service.users()
                .labels()
                .get(
                    userId=self.user_id,
                    id=label_data["id"],
                )
                .execute()
            )

            labels.append(GmailParser.parse_label(full_label))

        return labels

    def _get_label_id(self, label_name: str) -> str | None:
        """Get label ID by name."""
        if self._labels_cache is None:
            labels = self.get_labels()
            self._labels_cache = {l.name: l.id for l in labels}

        # Check if it's already an ID
        if label_name in self._labels_cache.values():
            return label_name

        return self._labels_cache.get(label_name)

    # ========== Send ==========

    def get_signature(self, send_as_email: str | None = None) -> str | None:
        """
        Get the account's email signature.

        Args:
            send_as_email: Specific send-as email (default: primary)

        Returns:
            HTML signature or None
        """
        try:
            email = send_as_email or self.email
            settings = (
                self.service.users()
                .settings()
                .sendAs()
                .get(
                    userId=self.user_id,
                    sendAsEmail=email,
                )
                .execute()
            )
            return settings.get("signature")
        except HttpError as e:
            logger.debug(f"Could not get signature for {send_as_email}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error getting signature: {e}")
            return None

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        html: bool = False,
        signature: bool = False,
        reply_to: str | None = None,
        thread_id: str | None = None,
        attachments: list[str] | None = None,
    ) -> Message:
        """
        Send an email.

        Args:
            to: Recipient email addresses
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            html: Whether body is HTML
            signature: Include account signature (appends to body)
            reply_to: Message ID to reply to
            thread_id: Thread ID (for threading)
            attachments: List of file paths to attach

        Returns:
            The sent message
        """
        # Append signature if requested
        final_body = body
        if signature:
            sig = self.get_signature()
            if sig:
                if html:
                    final_body = f"{body}<br><br>{sig}"
                else:
                    # Strip HTML from signature for plain text
                    import re

                    plain_sig = re.sub("<[^<]+?>", "", sig)
                    final_body = f"{body}\n\n{plain_sig}"

        # Build message
        if html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(final_body, "html"))
        else:
            message = MIMEText(final_body)

        message["To"] = ", ".join(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)

        # Encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body_dict = {"raw": raw}

        if thread_id:
            body_dict["threadId"] = thread_id

        # Send
        sent = (
            self.service.users()
            .messages()
            .send(
                userId=self.user_id,
                body=body_dict,
            )
            .execute()
        )

        return self.get_message(sent["id"])

    # ========== Profile ==========

    def get_profile(self) -> dict:
        """Get authenticated user's profile."""
        return self.service.users().getProfile(userId=self.user_id).execute()

    @property
    def email(self) -> str:
        """Get authenticated user's email address."""
        return self.get_profile().get("emailAddress", "")

    # ========== Internal modification methods ==========

    def _modify_labels(
        self,
        message_id: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        """Internal: modify labels on a message."""
        body = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove

        if body:
            self.service.users().messages().modify(
                userId=self.user_id,
                id=message_id,
                body=body,
            ).execute()

    def _trash_message(self, message_id: str) -> None:
        """Internal: trash a message."""
        self.service.users().messages().trash(
            userId=self.user_id,
            id=message_id,
        ).execute()

    def _untrash_message(self, message_id: str) -> None:
        """Internal: untrash a message."""
        self.service.users().messages().untrash(
            userId=self.user_id,
            id=message_id,
        ).execute()

    def _download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Internal: download attachment content."""
        attachment = (
            self.service.users()
            .messages()
            .attachments()
            .get(
                userId=self.user_id,
                messageId=message_id,
                id=attachment_id,
            )
            .execute()
        )

        return base64.urlsafe_b64decode(attachment.get("data", ""))

    # ========== Parsing ==========

    def _parse_message(self, data: dict, include_body: bool = True) -> Message:
        """Parse Gmail API response to Message object."""
        # Use centralized parser
        msg = GmailParser.parse_message(data, include_body)

        # Link message and attachments to this client for fluent methods
        msg._gmail = self
        for att in msg.attachments:
            att._gmail = self

        return msg
