"""Gmail response parsers - converts API responses to domain entities."""

import base64
from datetime import datetime
from email.utils import parsedate_to_datetime

from gsuite_gmail.label import Label, LabelType
from gsuite_gmail.message import Attachment, Message


class GmailParser:
    """Parser for Gmail API responses."""

    @staticmethod
    def parse_message(
        data: dict,
        include_body: bool = True,
    ) -> Message:
        """
        Parse Gmail API response to Message entity.

        Args:
            data: Raw API response dict
            include_body: Whether to parse body content

        Returns:
            Message entity
        """
        payload = data.get("payload", {})
        headers = payload.get("headers", [])

        def get_header(name: str) -> str:
            for h in headers:
                if h.get("name", "").lower() == name.lower():
                    return h.get("value", "")
            return ""

        # Parse date
        date = GmailParser._parse_date(get_header("Date"), data.get("internalDate"))

        # Parse body and attachments
        plain, html, attachments = None, None, []
        if include_body:
            plain, html, attachments = GmailParser._parse_payload(payload, data["id"])

        return Message(
            id=data["id"],
            thread_id=data.get("threadId", data["id"]),
            subject=get_header("Subject"),
            sender=get_header("From"),
            recipient=get_header("To"),
            cc=[addr.strip() for addr in get_header("Cc").split(",") if addr.strip()],
            date=date,
            snippet=data.get("snippet", ""),
            plain=plain,
            html=html,
            labels=data.get("labelIds", []),
            attachments=attachments,
        )

    @staticmethod
    def parse_label(data: dict) -> Label:
        """
        Parse Gmail API response to Label entity.

        Args:
            data: Raw API response dict

        Returns:
            Label entity
        """
        return Label(
            id=data["id"],
            name=data.get("name", data["id"]),
            type=LabelType.SYSTEM if data.get("type") == "system" else LabelType.USER,
            messages_total=data.get("messagesTotal", 0),
            messages_unread=data.get("messagesUnread", 0),
            threads_total=data.get("threadsTotal", 0),
            threads_unread=data.get("threadsUnread", 0),
        )

    @staticmethod
    def _parse_date(date_header: str, internal_date: str | None) -> datetime | None:
        """Parse date from header or internal timestamp."""
        if date_header:
            try:
                return parsedate_to_datetime(date_header)
            except (ValueError, TypeError):
                pass

        if internal_date:
            try:
                return datetime.fromtimestamp(int(internal_date) / 1000)
            except (ValueError, TypeError):
                pass

        return None

    @staticmethod
    def _parse_payload(
        payload: dict,
        message_id: str,
    ) -> tuple[str | None, str | None, list[Attachment]]:
        """
        Parse message payload for body content and attachments.

        Args:
            payload: Message payload dict
            message_id: Parent message ID

        Returns:
            Tuple of (plain_text, html, attachments)
        """
        plain = None
        html = None
        attachments = []

        def extract_parts(part: dict) -> None:
            nonlocal plain, html

            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")

            # Text content
            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    if mime_type == "text/plain" and not plain:
                        plain = decoded
                    elif mime_type == "text/html" and not html:
                        html = decoded
                except Exception:
                    pass

            # Attachments
            filename = part.get("filename")
            attachment_id = body.get("attachmentId")
            if filename and attachment_id:
                attachments.append(
                    Attachment(
                        id=attachment_id,
                        filename=filename,
                        mime_type=mime_type,
                        size=body.get("size", 0),
                        _message_id=message_id,
                    )
                )

            # Recurse into nested parts
            for sub_part in part.get("parts", []):
                extract_parts(sub_part)

        extract_parts(payload)
        return plain, html, attachments
