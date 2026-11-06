"""Building outgoing messages: MIME structure, attachments and the API body."""

import base64
import mimetypes
import os
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from gsuite_gmail._html import html_to_text

# A file path, or (filename, content) for data already in memory
OutgoingAttachment = str | os.PathLike[str] | tuple[str, bytes]


def prefixed(subject: str, prefix: str) -> str:
    """'Re: x' stays as is (any case); otherwise add the prefix."""
    return subject if subject.lower().startswith(prefix.lower()) else f"{prefix} {subject}"


def with_signature(body: str, signature: str, html: bool) -> str:
    """Append the (HTML) account signature, as text when the body is plain."""
    return f"{body}<br><br>{signature}" if html else f"{body}\n\n{html_to_text(signature)}"


def attach(message: EmailMessage, item: OutgoingAttachment) -> None:
    """Add a path or a (filename, bytes) pair as an attachment, typed by extension."""
    if isinstance(item, tuple):
        filename, content = item
    else:
        path = Path(item)
        filename, content = path.name, path.read_bytes()
    try:
        guessed = mimetypes.guess_type(filename)[0]
    except ValueError:
        # guess_type parses the name as a URL: "//[x.pdf" is a bad IPv6 host
        guessed = None
    mime_type = guessed or "application/octet-stream"
    maintype, subtype = mime_type.split("/", 1)
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)


@dataclass(frozen=True)
class MessageSpec:
    """What to send.

    ``in_reply_to``/``references`` are the threading headers: without them the
    recipient sees a new conversation even though it's in the sender's thread.
    """

    to: Sequence[str]
    subject: str
    body: str
    cc: Sequence[str] | None = None
    bcc: Sequence[str] | None = None
    html: bool = False
    attachments: Sequence[OutgoingAttachment] | None = None
    in_reply_to: str | None = None
    references: str | None = None


def build_message(spec: MessageSpec) -> EmailMessage:
    """The MIME message; an HTML body also gets a plain-text alternative."""
    message = EmailMessage()
    message["To"] = ", ".join(spec.to)
    if spec.cc:
        message["Cc"] = ", ".join(spec.cc)
    if spec.bcc:
        message["Bcc"] = ", ".join(spec.bcc)
    if spec.in_reply_to:
        message["In-Reply-To"] = spec.in_reply_to
        message["References"] = f"{spec.references or ''} {spec.in_reply_to}".strip()
    message["Subject"] = spec.subject

    if spec.html:
        message.set_content(html_to_text(spec.body))
        message.add_alternative(spec.body, subtype="html")
    else:
        message.set_content(spec.body)

    for item in spec.attachments or []:
        attach(message, item)
    return message


def encode_for_api(message: EmailMessage, thread_id: str | None = None) -> dict[str, Any]:
    """The users.messages.send / drafts.create body: {"raw", "threadId"}."""
    body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")}
    if thread_id:
        body["threadId"] = thread_id
    return body
