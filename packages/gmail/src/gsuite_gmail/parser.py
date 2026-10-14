"""Gmail response parsers - converts API responses to domain entities."""

import base64
import logging
import re
from datetime import UTC, datetime
from email.message import Message as EmailHeaders
from email.utils import formataddr, getaddresses, parsedate_to_datetime

from gsuite_gmail.label import Label, LabelType
from gsuite_gmail.message import Attachment, Message

logger = logging.getLogger(__name__)

# RFC 5322 specials that force a display name into a quoted string
_SPECIALS = re.compile(r'[][\\()<>@,:;".]')


def _format_address(name: str, addr: str) -> str:
    """``formataddr`` that never raises.

    ``formataddr`` rejects non-ASCII addresses (internationalized email,
    RFC 6532, e.g. ``josé@example.com``); those are formatted as readable
    Unicode instead.
    """
    try:
        return formataddr((name, addr))
    except UnicodeError:
        pass
    if not name:
        return addr
    if _SPECIALS.search(name):
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        name = f'"{escaped}"'
    return f"{name} <{addr}>"


def _b64decode(data: str, message_id: str) -> bytes | None:
    """Decode a Gmail body (base64url, padding optional); None if it is not base64.

    Only the message id is logged: the body itself is untrusted content.
    """
    try:
        return base64.urlsafe_b64decode(data)
    except (ValueError, TypeError):  # binascii.Error is a ValueError
        pass
    try:
        # Gmail sometimes sends unpadded base64url; re-pad and retry
        stripped = "".join(data.split()).rstrip("=")
        return base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4))
    except (ValueError, TypeError):
        logger.warning("Message %s: part body is not valid base64; skipped", message_id)
        return None


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
        headers = GmailParser._headers(payload)

        def get_header(name: str) -> str:
            return headers.get(name.lower(), "")

        date = GmailParser._parse_date(get_header("Date"), data.get("internalDate"))

        plain: str | None = None
        html: str | None = None
        attachments: list[Attachment] = []
        if include_body:
            plain, html, attachments = GmailParser._parse_payload(payload, data["id"])

        return Message(
            id=data["id"],
            thread_id=data.get("threadId", data["id"]),
            subject=get_header("Subject"),
            sender=get_header("From"),
            recipient=get_header("To"),
            cc=GmailParser._addresses(get_header("Cc")),
            bcc=GmailParser._addresses(get_header("Bcc")),
            date=date,
            snippet=data.get("snippet", ""),
            plain=plain,
            html=html,
            labels=data.get("labelIds", []),
            attachments=attachments,
            reply_to=get_header("Reply-To") or None,
            rfc822_message_id=get_header("Message-ID") or None,
            references=get_header("References") or None,
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
    def _headers(part: dict) -> dict[str, str]:
        """Headers of a part, keyed by lowercase name (first occurrence wins)."""
        result: dict[str, str] = {}
        for header in part.get("headers", []):
            result.setdefault(header.get("name", "").lower(), header.get("value", ""))
        return result

    @staticmethod
    def _addresses(value: str) -> list[str]:
        """Split an address header; '"Doe, John" <j@x.com>' stays one entry."""
        if not value:
            return []
        return [_format_address(name, addr) for name, addr in getaddresses([value]) if addr]

    @staticmethod
    def _parse_date(date_header: str, internal_date: str | None) -> datetime | None:
        """Parse date from header or internal timestamp; always timezone-aware.

        A Date header without a usable zone (``-0000``, or none at all) is taken
        as UTC: RFC 5322 defines ``-0000`` as "UTC, local zone unknown".
        """
        if date_header:
            try:
                date = parsedate_to_datetime(date_header)
            except (ValueError, TypeError):
                pass
            else:
                return date if date.tzinfo is not None else date.replace(tzinfo=UTC)

        if internal_date:
            try:
                # Milliseconds since the epoch, UTC (was a naive local time)
                return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
            except (ValueError, TypeError, OverflowError, OSError):
                pass  # not a number, or outside the range datetime supports

        return None

    @staticmethod
    def _decode_text(data: str, headers: dict[str, str], message_id: str = "") -> str:
        """Decode a text part in the charset its Content-Type declares.

        Never raises: a body that is not base64 decodes to "", and a charset
        Python cannot decode with ``errors="replace"`` (unknown, or a codec
        such as ``idna`` or ``undefined``) falls back to UTF-8.
        """
        raw = _b64decode(data, message_id)
        if raw is None:
            return ""
        content_type = EmailHeaders()
        content_type["Content-Type"] = headers.get("content-type", "text/plain")
        charset = content_type.get_content_charset() or "utf-8"
        try:
            return raw.decode(charset, errors="replace")
        except (LookupError, ValueError):  # unknown/unusable codec; UnicodeError too
            logger.warning("Message %s: unusable charset in a text part; using UTF-8", message_id)
            return raw.decode("utf-8", errors="replace")

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

        # Depth-first, in document order, without recursion: nesting depth is
        # attacker-controlled and would otherwise raise RecursionError.
        stack = [payload]
        while stack:
            part = stack.pop()
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")
            headers = GmailParser._headers(part)
            filename = part.get("filename")

            if filename:
                # Any named part is an attachment, even a text/plain one that
                # arrives inline: it used to be taken for the message body.
                attachments.append(
                    Attachment(
                        id=body.get("attachmentId") or part.get("partId", ""),
                        filename=filename,
                        mime_type=mime_type,
                        size=body.get("size", 0),
                        _message_id=message_id,
                        _data=_b64decode(data, message_id)
                        if data and not body.get("attachmentId")
                        else None,
                    )
                )
            elif data and mime_type == "text/plain" and plain is None:
                plain = GmailParser._decode_text(data, headers, message_id)
            elif data and mime_type == "text/html" and html is None:
                html = GmailParser._decode_text(data, headers, message_id)

            stack.extend(reversed(part.get("parts", [])))

        return plain, html, attachments
