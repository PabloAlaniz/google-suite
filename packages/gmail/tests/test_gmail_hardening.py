"""Regression tests for hostile input: HTML-to-text, message payloads, query builder."""

import base64
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from gsuite_gmail import query as q
from gsuite_gmail.client import _html_to_text
from gsuite_gmail.message import Message
from gsuite_gmail.parser import GmailParser

# ---------------------------------------------------------------- _html_to_text

# ~140 KB each. The regex-based version took seconds to minutes on these.
PATHOLOGICAL_HTML = [
    "<script" * 20_000,
    "<style" * 23_334,
    "<SCRIPT>" * 17_500 + "</style>",
    "<" * 140_000,
    "<a" * 70_000,
    "<!--" * 35_000,
    "<br" + " " * 140_000,
    "<p " * 46_667,
]


@pytest.mark.parametrize("markup", PATHOLOGICAL_HTML, ids=lambda m: repr(m[:8]))
def test_html_to_text_is_linear_on_unclosed_markup(markup):
    start = time.perf_counter()
    _html_to_text(markup)
    assert time.perf_counter() - start < 0.5


def test_html_to_text_output_unchanged_for_normal_html():
    markup = (
        "<html><head><style>p { color: red }</style><script>alert(1)</script></head>"
        "<body><h1>Title</h1><p>Hello&nbsp;<b>world</b> &amp; you</p>"
        "<div>Line<br>break<BR/>again</div><ul><li>one</li><li>two</li></ul>"
        "<p></p><p></p><p>end &lt;tag&gt;</p></body></html>"
    )
    assert _html_to_text(markup) == (
        "Title\nHello\xa0world & you\nLine\nbreak\nagain\none\ntwo\n\nend <tag>"
    )


def test_html_to_text_keeps_unclosed_script_text():
    # Unchanged rough behavior: only complete script/style elements are dropped
    assert _html_to_text("a<script>b") == "ab"
    assert _html_to_text("x < y and y > z") == "x  z"


# ------------------------------------------------------------------------ query


@pytest.mark.parametrize(
    ("built", "expected"),
    [
        (q.from_("a@b.com OR label:x"), 'from:"a@b.com OR label:x"'),
        (q.to("x@y.com\tin:trash"), 'to:"x@y.com\tin:trash"'),
        (q.subject('a" OR from:x'), 'subject:"a OR from:x"'),
        (q.subject('say "hi"'), 'subject:"say hi"'),
        (q.subject('"quoted"'), "subject:quoted"),
        (q.label('My" Label'), 'label:"My Label"'),
        (q.label("(work)"), 'label:"(work)"'),
        (q.filename("a.pdf {b}"), 'filename:"a.pdf {b}"'),
        (q.category("social -in:spam"), 'category:"social -in:spam"'),
        (q.after("2024/01/01 OR x"), 'after:"2024/01/01 OR x"'),
        (q.before("2024/01/01"), "before:2024/01/01"),
    ],
)
def test_query_values_cannot_inject_terms(built, expected):
    assert str(built) == expected


def test_construct_query_quotes_values():
    built = q.construct_query(
        from_="a@b.com OR x", to="c@d.com", subject='hi" OR x', labels=["My Projects", "W)"]
    )
    assert str(built) == (
        'from:"a@b.com OR x" to:c@d.com subject:"hi OR x" label:"My Projects" label:"W)"'
    )


# ----------------------------------------------------------------------- parser


def _b64(raw: bytes, *, pad: bool = True) -> str:
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return encoded if pad else encoded.rstrip("=")


def _parse(payload: dict[str, Any], **extra: Any) -> Message:
    return GmailParser.parse_message({"id": "m1", "payload": payload, **extra})


@pytest.mark.parametrize("data", ["Secre", "SecretSec", "SecretSecré"])
def test_invalid_base64_body_is_empty_and_logged(data, caplog):
    message = _parse({"mimeType": "text/plain", "body": {"data": data}})
    assert message.plain == ""
    (record,) = caplog.records
    assert "m1" in record.getMessage()
    assert data not in record.getMessage()  # no payload content in the log


def test_unpadded_base64_body_is_decoded():
    message = _parse({"mimeType": "text/plain", "body": {"data": _b64(b"abcd", pad=False)}})
    assert message.plain == "abcd"


def test_invalid_base64_inline_attachment_has_no_data():
    payload = {"mimeType": "image/png", "filename": "x.png", "body": {"data": "a", "size": 1}}
    (attachment,) = _parse(payload).attachments
    assert attachment.filename == "x.png"
    assert attachment._data is None


@pytest.mark.parametrize("internal_date", ["9" * 20, "9" * 400, "9" * 5000, "-" + "9" * 20])
def test_out_of_range_internal_date_is_none(internal_date):
    assert _parse({}, internalDate=internal_date).date is None


@pytest.mark.parametrize("zone", ["-0000", ""])
def test_date_without_known_zone_is_utc(zone):
    date = f"Mon, 26 Jan 2026 10:00:00 {zone}".strip()
    message = _parse({"headers": [{"name": "Date", "value": date}]})
    assert message.date == datetime(2026, 1, 26, 10, tzinfo=UTC)
    assert message.date.tzinfo is not None


def test_date_with_zone_is_unchanged():
    message = _parse({"headers": [{"name": "Date", "value": "Mon, 26 Jan 2026 10:00:00 +0200"}]})
    assert message.date == datetime(2026, 1, 26, 10, tzinfo=timezone(timedelta(hours=2)))


def test_deeply_nested_parts_are_walked_in_order():
    leaf = {"mimeType": "text/plain", "body": {"data": _b64(b"deep")}}
    payload: dict[str, Any] = {
        "mimeType": "multipart/mixed",
        "parts": [leaf, {"mimeType": "image/png", "filename": "last.png", "body": {}}],
    }
    for depth in range(5000):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [{"filename": f"{depth}.txt", "body": {}}, payload],
        }
    message = _parse(payload)
    assert message.plain == "deep"
    names = [attachment.filename for attachment in message.attachments]
    assert names == [f"{depth}.txt" for depth in reversed(range(5000))] + ["last.png"]


# punycode is not here: it decodes anything (to garbage) without raising
@pytest.mark.parametrize("charset", ["idna", "undefined", "ascii\x00", "bogus"])
def test_unusable_charset_falls_back_to_utf8(charset):
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": f"text/plain; charset={charset}"}],
        "body": {"data": _b64("héllo".encode())},
    }
    assert _parse(payload).plain == "héllo"


def test_non_ascii_addresses_are_kept_readable():
    cc = 'josé@example.com, José <jö@example.com>, "Doe, Jü" <dj@exämple.com>, a@b.com'
    message = _parse({"headers": [{"name": "Cc", "value": cc}, {"name": "Bcc", "value": "\x80"}]})
    assert message.cc == [
        "josé@example.com",
        "José <jö@example.com>",
        '"Doe, Jü" <dj@exämple.com>',
        "a@b.com",
    ]
    assert message.bcc == ["\x80"]
