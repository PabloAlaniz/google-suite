"""GmailParser against realistic MIME structures.

Fixtures are built with the stdlib email package and converted to the
payload shape the Gmail API returns, instead of hand-written dicts.
"""

import base64
from datetime import UTC, datetime
from email.message import EmailMessage
from email.message import Message as RawMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gsuite_gmail.parser import GmailParser


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def to_payload(part: RawMessage, part_id: str = "", inline_limit: int = 64) -> dict:
    """Convert an email part to the Gmail API payload format."""
    payload = {
        "partId": part_id,
        "mimeType": part.get_content_type(),
        "filename": part.get_filename() or "",
        "headers": [{"name": k, "value": str(v)} for k, v in part.items()],
        "body": {"size": 0},
    }
    if part.is_multipart():
        payload["parts"] = [
            to_payload(sub, f"{part_id}.{i}".lstrip("."), inline_limit)
            for i, sub in enumerate(part.get_payload())
        ]
    else:
        data = part.get_payload(decode=True) or b""
        payload["body"]["size"] = len(data)
        # Gmail inlines small bodies and gives big attachments an ID
        if payload["filename"] and len(data) > inline_limit:
            payload["body"]["attachmentId"] = f"att-{part_id}"
        else:
            payload["body"]["data"] = b64(data)
    return payload


def parse(message: RawMessage, **extra):
    return GmailParser.parse_message(
        {"id": "m1", "threadId": "t1", "payload": to_payload(message), **extra}
    )


def test_multipart_alternative_inside_mixed():
    outer = EmailMessage()
    outer["Subject"] = "Hola"
    outer.set_content("plain body")
    outer.add_alternative("<p>html body</p>", subtype="html")
    outer.add_attachment(b"x" * 100, maintype="application", subtype="pdf", filename="report.pdf")

    msg = parse(outer)

    assert msg.plain.strip() == "plain body"
    assert msg.html.strip() == "<p>html body</p>"
    assert [(a.filename, a.mime_type, a.id) for a in msg.attachments] == [
        ("report.pdf", "application/pdf", "att-1")
    ]


def test_latin1_body_is_decoded_with_its_charset():
    part = MIMEText("Canción ñandú", "plain", "iso-8859-1")
    assert parse(part).plain == "Canción ñandú"  # was 'Canci�n �and�'


def test_windows_1252_html():
    part = MIMEText("<p>“quoted” – dash</p>", "html", "windows-1252")
    assert parse(part).html == "<p>“quoted” – dash</p>"


def test_unknown_charset_falls_back_to_utf8():
    part = MIMEText("hola", "plain", "utf-8")
    part.replace_header("Content-Type", 'text/plain; charset="x-made-up"')
    assert parse(part).plain == "hola"


def test_text_attachment_is_not_the_body():
    mixed = MIMEMultipart("mixed")
    attachment = MIMEText("ATTACHMENT TEXT", "plain")
    attachment.add_header("Content-Disposition", "attachment", filename="notes.txt")
    mixed.attach(attachment)  # comes first, inline-sized
    mixed.attach(MIMEText("real body", "plain"))

    msg = parse(mixed)

    assert msg.plain == "real body"
    (att,) = msg.attachments
    assert att.filename == "notes.txt"
    # Small attachments arrive inline; download() returns them without a request
    assert att.download() == b"ATTACHMENT TEXT"


def test_inline_image_is_an_attachment():
    related = EmailMessage()
    related.set_content("<p><img src='cid:logo'></p>", subtype="html")
    related.add_related(
        b"\x89PNG" * 40, maintype="image", subtype="png", cid="<logo>", filename="logo.png"
    )

    msg = parse(related)

    assert msg.html.startswith("<p><img")
    assert [a.filename for a in msg.attachments] == ["logo.png"]


def test_forwarded_message_body_does_not_override_outer():
    outer = EmailMessage()
    outer.set_content("my note")
    inner = EmailMessage()
    inner["Subject"] = "original"
    inner.set_content("forwarded text")
    outer.add_attachment(inner)  # message/rfc822

    assert parse(outer).plain.strip() == "my note"


def test_headers():
    msg = EmailMessage()
    msg["From"] = "Ana <ana@example.com>"
    msg["To"] = "me@example.com"
    msg["Cc"] = '"Doe, John" <j@example.com>, bo@example.com'
    msg["Reply-To"] = "list@example.com"
    msg["Message-ID"] = "<abc@example.com>"
    msg["References"] = "<root@example.com>"
    msg["Date"] = "Mon, 05 Oct 2026 10:00:00 -0300"
    msg.set_content("x")

    parsed = parse(msg, labelIds=["INBOX", "UNREAD"])

    assert parsed.cc == ['"Doe, John" <j@example.com>', "bo@example.com"]  # was split at the comma
    assert parsed.reply_to == "list@example.com"
    assert parsed.rfc822_message_id == "<abc@example.com>"
    assert parsed.references == "<root@example.com>"
    assert parsed.date == datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    assert parsed.is_unread


def test_internal_date_is_utc_aware():
    msg = GmailParser.parse_message(
        {"id": "m", "internalDate": "1700000000000", "payload": {"headers": []}}
    )
    assert msg.date == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_metadata_only_skips_body():
    part = MIMEText("body")
    assert parse(part).plain == "body"
    assert (
        GmailParser.parse_message(
            {"id": "m1", "payload": to_payload(part)}, include_body=False
        ).plain
        is None
    )
