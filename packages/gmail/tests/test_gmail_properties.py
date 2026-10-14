"""Property-based tests for gsuite_gmail (invariants in gsuite_gmail._testing.properties).

Tests suffixed with a bug id are regressions for fixed bugs: B1 (_html_to_text
quadratic), B2 (query injection), B3a-d (parser not total), B9-gmail-1 (charset
codec escapes the decoder), B9-gmail-2 (non-ASCII Cc/Bcc address).
"""

import base64
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any

from hypothesis import example, given
from hypothesis import strategies as st

from gsuite_gmail._testing.properties import (
    QUERY_OPERATORS,
    check_compose_roundtrip,
    check_construct_query_terms,
    check_html_to_text_plain_passthrough,
    check_html_to_text_scales,
    check_html_to_text_strips_tags,
    check_parse_message,
    check_query_combinators,
    check_query_single_term,
)
from gsuite_gmail.client import _html_to_text

# ---------------------------------------------------------------- _html_to_text

html_fragments = st.sampled_from(
    [
        *("<", ">", "</", "<p>", "</p>", "<br/>", "<script>", "</script>", "<style", "<!--"),
        *("-->", "<div class='x'>", "</div>", "&", "&lt;", "&gt;", "&amp;", "\n", " ", "a"),
    ]
)
html_like = st.lists(html_fragments | st.text(max_size=5), max_size=30).map("".join)


@given(html_like)
@example("<<a>b>")
@example("<script>x</script><style>y")
def test_html_to_text_strips_tags(markup):
    check_html_to_text_strips_tags(markup)


@given(st.text(max_size=200))
@example("a\n\n\n\nb")
@example("  \u2028 x \xa0")
def test_html_to_text_plain_passthrough(text):
    check_html_to_text_plain_passthrough(text)


# Each is ~100-140 KB of hostile HTML; linear code handles any of them in ~1 ms.
# The test stops at the first slow input, so it costs ~1.5 s while the bug is there.
B1_INPUTS = [
    "<script" * 10_000,  # (?is)<(script|style).*?</\1> rescans to the end per "<script"
    "<style" * 10_000,
    "<" * 70_000,  # <[^>]+> rescans to the end per unclosed "<"
    "<a" * 35_000,
    "<!--" * 35_000,
]


def test_html_to_text_linear_time_b1():
    for markup in B1_INPUTS:
        start = time.perf_counter()
        _html_to_text(markup)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"{markup[:8]!r}*{len(markup)}: {elapsed:.2f}s"


@given(st.text(max_size=12))
@example("<script")
@example("<style")
@example("<a")
@example("<!--")
def test_html_to_text_scales(fragment):
    check_html_to_text_scales(fragment)


# ----------------------------------------------------------------------- parser


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


# Dates the parser must turn into aware datetimes (any real UTC offset)
aware_dates = st.builds(
    lambda dt, minutes: format_datetime(dt.replace(tzinfo=timezone(timedelta(minutes=minutes)))),
    st.datetimes(min_value=datetime(1970, 1, 2), max_value=datetime(9999, 12, 30)),
    st.integers(-23 * 60 - 59, 23 * 60 + 59),
)
# Unparseable dates: no Nd digits, so parsedate can't read a day or year
junk_dates = st.text(alphabet=st.characters(exclude_categories=("Nd", "Cs")), max_size=30)
charsets = st.sampled_from(
    ["utf-8", "latin-1", "utf-16", "us-ascii", "bogus", "base64", "idna", "undefined"]
)
content_types = st.one_of(
    st.builds(lambda cs: f'text/plain; charset="{cs}"', charsets),
    st.text(max_size=30),
)
header_values = st.text(max_size=40)
headers = st.lists(
    st.one_of(
        st.builds(lambda v: {"name": "Date", "value": v}, aware_dates | junk_dates),
        st.builds(lambda v: {"name": "Content-Type", "value": v}, content_types),
        st.builds(
            lambda n, v: {"name": n, "value": v},
            st.sampled_from(["Subject", "From", "To", "Reply-To", "Message-ID"])
            | st.text(max_size=10),
            header_values,
        ),
        st.builds(
            lambda n, v: {"name": n, "value": v},
            st.sampled_from(["Cc", "Bcc"]),
            st.text(max_size=40),
        ),
    ),
    max_size=6,
)
bodies = st.fixed_dictionaries(
    {},
    optional={
        "data": st.binary(max_size=60).map(b64) | st.text(max_size=20),
        "attachmentId": st.text(max_size=8),
        "size": st.integers(0, 10**9),
    },
)
mime_types = st.sampled_from(
    ["text/plain", "text/html", "multipart/mixed", "multipart/alternative", "image/png"]
) | st.text(max_size=12)


def part(children: st.SearchStrategy[list[dict[str, Any]]]) -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries(
        {},
        optional={
            "mimeType": mime_types,
            "headers": headers,
            "body": bodies,
            "filename": st.none() | st.text(max_size=10),
            "partId": st.text(max_size=4),
            "parts": children,
        },
    )


payloads = st.recursive(
    part(st.just([])),
    lambda inner: part(st.lists(inner, max_size=3)),
    max_leaves=12,
)
messages = st.fixed_dictionaries(
    {"id": st.text(min_size=1, max_size=8)},
    optional={
        "threadId": st.text(max_size=8),
        "internalDate": st.integers(0, 10**30).map(str),
        "labelIds": st.lists(st.text(max_size=8), max_size=3),
        "snippet": st.text(max_size=20),
        "payload": payloads,
    },
)


@given(messages, st.booleans())
def test_parse_message_total(data, include_body):
    check_parse_message(data, include_body)


def _text_message(data: str) -> dict[str, Any]:
    return {"id": "m", "payload": {"mimeType": "text/plain", "body": {"data": data}}}


@given(st.just("a"))
@example("a")
def test_parse_message_invalid_base64_body_b3a(data):
    check_parse_message(_text_message(data))


@given(st.just("a"))
@example("a")
def test_parse_message_invalid_base64_attachment_b3a(data):
    payload = {"mimeType": "image/png", "filename": "x.png", "body": {"data": data}}
    check_parse_message({"id": "m", "payload": payload})


@given(st.integers(10**19, 10**30).map(str))
@example("9" * 400)  # OverflowError on every platform
@example("9" * 20)  # OSError on macOS
def test_parse_message_huge_internal_date_b3b(internal_date):
    check_parse_message({"id": "m", "internalDate": internal_date})


# Found by ClusterFuzzLite: parsedate_to_datetime raises OverflowError when a
# field doesn't fit a C long/int
@given(
    st.integers(10**19, 10**30),
    st.sampled_from(["{n} Jan 2024 00:00:00", "01 Jan {n} 00:00:00", "01 Jan 2024 {n}:00:00"]),
)
@example(10**20, "01 Jan 2024 00:00:00 +{n}")
def test_parse_message_overflowing_date_header(number, template):
    payload = {"headers": [{"name": "Date", "value": "Mon, " + template.format(n=number)}]}
    check_parse_message({"id": "m", "payload": payload})


@given(st.sampled_from(["-0000", ""]))
@example("-0000")
def test_parse_message_naive_date_b3c(zone):
    date = f"Mon, 28 Jan 2026 10:00:00 {zone}".strip()
    check_parse_message({"id": "m", "payload": {"headers": [{"name": "Date", "value": date}]}})


def test_parse_message_deep_nesting_b3d():
    payload: dict[str, Any] = {"mimeType": "text/plain"}
    for _ in range(2000):
        payload = {"mimeType": "multipart/mixed", "parts": [payload]}
    # Fail outside the except block: rendering the ~1000-frame RecursionError
    # traceback (even as a chained __context__) takes pytest ~20 s.
    recursed = False
    try:
        check_parse_message({"id": "m", "payload": payload})
    except RecursionError:
        recursed = True
    assert not recursed, "RecursionError on 2000 nested parts"


@given(st.sampled_from(["idna", "punycode", "undefined"]))
@example("idna")  # UnicodeError: Unsupported error handling replace
@example("undefined")  # UnicodeError: undefined encoding
@example("ascii\x00")  # ValueError: embedded null character
def test_parse_message_hostile_charset_b9_gmail_1(charset):
    payload = {
        "mimeType": "text/plain",
        "headers": [{"name": "Content-Type", "value": f"text/plain; charset={charset}"}],
        "body": {"data": b64(b"\xff\xfe\x80abc")},
    }
    check_parse_message({"id": "m", "payload": payload})


@given(st.sampled_from(["Cc", "Bcc"]), st.just("josé@example.com"))
@example("Cc", "josé@example.com")  # internationalized (RFC 6532) address
@example("Bcc", "\x80")
def test_parse_message_non_ascii_cc_b9_gmail_2(header, value):
    payload = {"headers": [{"name": header, "value": value}]}
    check_parse_message({"id": "m", "payload": payload})


# ------------------------------------------------------------------------ query

# Values Gmail can take unquoted: no whitespace, quotes or grouping characters
unquoted_values = st.text(
    alphabet=st.characters(
        exclude_categories=("Zs", "Zl", "Zp", "Cc", "Cs"), exclude_characters='"(){}'
    ),
    max_size=20,
)
# subject/label quote values with spaces, so plain spaces are fine there too
spaced_values = st.lists(unquoted_values, min_size=1, max_size=4).map(" ".join)


@given(st.sampled_from(QUERY_OPERATORS), unquoted_values)
@example("from", "sender@example.com")
def test_query_single_term(operator, value):
    check_query_single_term(operator, value)


@given(st.sampled_from(["subject", "label"]), spaced_values)
@example("subject", "hello world")
@example("label", "My Projects")
def test_query_single_term_quoted(operator, value):
    check_query_single_term(operator, value)


@given(unquoted_values, spaced_values)
def test_query_combinators(left, right):
    check_query_combinators(left, right)


@given(
    st.none() | unquoted_values,
    st.none() | unquoted_values,
    st.none() | spaced_values,
    st.lists(spaced_values, max_size=3),
)
def test_construct_query_terms(from_, to, subject, labels):
    check_construct_query_terms(from_, to, subject, labels)


@given(st.sampled_from(["subject", "label"]), st.text(max_size=20))
@example("subject", 'a" OR from:x')
def test_query_quote_injection_b2(operator, value):
    check_query_single_term(operator, value)


@given(st.sampled_from(["from", "to", "filename", "category"]), st.text(max_size=20))
@example("from", "a@b.com OR label:x")
def test_query_whitespace_injection_b2(operator, value):
    check_query_single_term(operator, value)


# ---------------------------------------------------------------------- compose

addresses = st.builds(
    "{}@{}.com".format,
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=1, max_size=10),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
).filter(lambda a: not a.startswith(".") and ".." not in a and ".@" not in a)


@given(
    st.lists(addresses, min_size=1, max_size=3),
    st.text(max_size=80),
    st.lists(addresses, max_size=2),
    st.lists(st.text(min_size=1, max_size=20), max_size=2),
)
@example(["a@b.com"], "hi\r\nBcc: evil@x.com", [], [])
@example(["a@b.com\nBcc: evil@x.com"], "hi", [], [])
@example(["a@b.com"], "hi", [], ["f\r\nX-Evil: 1.txt"])
@example(["a@b.com"], "hi", [], ['"' * 40])  # found by ClusterFuzzLite
@example(["a@b.com"], "hi", [], ['"a\\"b"'])
def test_compose_roundtrip(to, subject, cc, attachment_names):
    check_compose_roundtrip(to, subject, cc, attachment_names)
