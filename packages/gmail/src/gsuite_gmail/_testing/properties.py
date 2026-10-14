"""Invariant checks for gsuite_gmail (HTML-to-text, message parser, query builder, compose).

Every ``check_*`` function takes concrete inputs, runs the code under test and
raises :class:`~gsuite_core._testing.PropertyViolation` when an invariant does
not hold. Any other exception escaping a check is a bug in the code under test.
They are shared by the Hypothesis tests and the atheris fuzz harnesses, so they
must accept arbitrary input of the declared types.
"""

import base64
import binascii
import email
import re
import time
from collections.abc import Callable, Sequence
from email import policy
from email.utils import getaddresses
from typing import Any, cast

from gsuite_core import GoogleAuth
from gsuite_core._testing import PropertyViolation, require
from gsuite_gmail import query
from gsuite_gmail.client import Gmail, _html_to_text
from gsuite_gmail.parser import GmailParser

_TAG = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------- _html_to_text


def check_html_to_text_strips_tags(markup: str) -> None:
    """The text alternative never contains markup.

    ``&lt;b&gt;`` legitimately becomes ``<b>`` (escaped text), so the check only
    applies to markup without entities.
    """
    text = _html_to_text(markup)
    require(isinstance(text, str), f"_html_to_text returned {type(text).__name__}")
    if "&" not in markup:
        tag = _TAG.search(text)
        require(tag is None, f"tag {tag and tag.group()!r} survived in {text!r}")


def check_html_to_text_plain_passthrough(text: str) -> None:
    """Plain text (no ``<`` or ``&``) only gets blank lines collapsed and stripped."""
    if "<" in text or "&" in text:
        return
    expected = re.sub(r"\n{3,}", "\n\n", text).strip()
    once = _html_to_text(text)
    require(once == expected, f"plain text {text!r} became {once!r}, expected {expected!r}")
    twice = _html_to_text(once)
    require(twice == once, f"not idempotent on plain text: {once!r} -> {twice!r}")


def _html_to_text_seconds(markup: str, size: int) -> float:
    big = markup * (size // len(markup) + 1)
    start = time.perf_counter()
    _html_to_text(big)
    return time.perf_counter() - start


def check_html_to_text_scales(markup: str, size: int = 200_000) -> None:
    """Converting ``markup`` repeated 8x longer takes about 8x as long, not 64x.

    Fuzzers only generate small inputs, where super-linear behavior costs
    microseconds; repeating the fragment exposes it. Comparing two sizes keeps
    the check independent of machine speed and instrumentation overhead; the
    absolute slack absorbs timer noise on fast inputs.
    """
    if not markup:
        return
    small = min(_html_to_text_seconds(markup, size // 8) for _ in range(2))
    large = _html_to_text_seconds(markup, size)
    require(
        large < 24 * small + 0.05,
        f"{markup[:20]!r}: {small:.3f}s at {size // 8} chars but {large:.2f}s at {size}",
    )


# ----------------------------------------------------------------------- parser


def _named_parts(payload: dict[str, Any]) -> int:
    """Parts (the payload itself included) carrying a filename, walked iteratively."""
    count = 0
    stack = [payload]
    while stack:
        part = stack.pop()
        if part.get("filename"):
            count += 1
        stack.extend(part.get("parts", []))
    return count


def check_parse_message(data: dict[str, Any], include_body: bool = True) -> None:
    """parse_message is total over Gmail-API-shaped dicts with attacker-controlled content.

    ``data`` must have the API's shape (an ``id`` string; ``payload`` with
    ``mimeType``/``headers``/``body``/``parts``/``filename``); every value in it
    may be arbitrary. No exception is acceptable: one hostile email must not
    break listing a mailbox.
    """
    message = GmailParser.parse_message(data, include_body=include_body)
    require(message.id == data["id"], f"id {message.id!r} != {data['id']!r}")
    require(
        message.thread_id == data.get("threadId", data["id"]),
        f"thread_id {message.thread_id!r} does not match {data.get('threadId')!r}",
    )
    require(
        message.date is None or message.date.tzinfo is not None,
        f"naive date {message.date!r} (Date header / internalDate must give aware datetimes)",
    )
    require(message.plain is None or isinstance(message.plain, str), "plain is not str")
    require(message.html is None or isinstance(message.html, str), "html is not str")
    if not include_body:
        require(
            message.plain is None and message.html is None and not message.attachments,
            "include_body=False still parsed the body",
        )
        return
    expected = _named_parts(data.get("payload", {}))
    require(
        len(message.attachments) == expected,
        f"{len(message.attachments)} attachments for {expected} parts with a filename",
    )
    for attachment in message.attachments:
        require(bool(attachment.filename), f"attachment without filename: {attachment!r}")


# ------------------------------------------------------------------------ query

_QUERY_BUILDERS: dict[str, Callable[[str], query.Query]] = {
    "from": query.from_,
    "to": query.to,
    "subject": query.subject,
    "label": query.label,
    "filename": query.filename,
    "category": query.category,
    "after": query.after,
    "before": query.before,
}
QUERY_OPERATORS = tuple(_QUERY_BUILDERS)

_OPENERS = {"(": ")", "{": "}"}


def top_level_terms(text: str) -> list[str]:
    """Split a Gmail query into top-level terms.

    Whitespace separates terms unless it is inside ``"..."`` or a ``(...)`` /
    ``{...}`` group. Unbalanced quotes or brackets raise PropertyViolation:
    the builder produced a query whose meaning depends on how Gmail recovers.
    """
    terms: list[str] = []
    current: list[str] = []
    closers: list[str] = []
    in_quote = False
    for char in text:
        if in_quote:
            in_quote = char != '"'
        elif char == '"':
            in_quote = True
        elif char in _OPENERS:
            closers.append(_OPENERS[char])
        elif char in ")}":
            require(bool(closers) and closers.pop() == char, f"unbalanced {char!r} in {text!r}")
        elif char.isspace() and not closers:
            if current:
                terms.append("".join(current))
                current = []
            continue
        current.append(char)
    require(not in_quote, f"unterminated quote in {text!r}")
    require(not closers, f"unclosed group in {text!r}")
    if current:
        terms.append("".join(current))
    return terms


def check_query_single_term(operator: str, value: str) -> None:
    """``<operator>(value)`` yields exactly one ``operator:`` term, whatever the value."""
    built = str(_QUERY_BUILDERS[operator](value))
    terms = top_level_terms(built)
    require(len(terms) == 1, f"{operator}({value!r}) -> {built!r} has {len(terms)} terms")
    require(terms[0].startswith(f"{operator}:"), f"{built!r} does not start with {operator}:")


def check_query_combinators(left: str, right: str) -> None:
    """``&`` concatenates terms; ``|`` and ``~`` keep everything grouped."""
    a, b = query.from_(left), query.subject(right)
    n_a, n_b = len(top_level_terms(str(a))), len(top_level_terms(str(b)))
    both = top_level_terms(str(a & b))
    require(len(both) == n_a + n_b, f"{str(a & b)!r} has {len(both)} terms")
    either = top_level_terms(str(a | b))
    require(len(either) == 3 and either[1] == "OR", f"bad OR query {str(a | b)!r}")
    negated = top_level_terms(str(~a))
    require(len(negated) == 1, f"bad negation {str(~a)!r}")


def check_construct_query_terms(
    from_: str | None, to: str | None, subject: str | None, labels: Sequence[str]
) -> None:
    """construct_query yields one term per given field and per label."""
    built = str(query.construct_query(from_=from_, to=to, subject=subject, labels=list(labels)))
    terms = top_level_terms(built)
    expected = [
        op for op, value in (("from", from_), ("to", to), ("subject", subject)) if value
    ] + ["label"] * len(labels)
    require(len(terms) == len(expected), f"{built!r}: {len(terms)} terms, expected {expected}")
    for term, op in zip(terms, expected, strict=True):
        require(term.startswith(f"{op}:"), f"term {term!r} should be {op}:")


# ---------------------------------------------------------------------- compose

_COMPOSE_HEADERS = {"to", "cc", "subject", "mime-version", "content-type"}
_COMPOSE_HEADERS_OPTIONAL = {"content-transfer-encoding"}


def _parsed_filename(name: str) -> str:
    """What the stdlib parser returns for a correctly encoded ``filename=name``.

    It strips surrounding whitespace and, like email.utils.unquote, one pair of
    enclosing angle brackets.
    """
    name = name.strip()
    if len(name) > 1 and name.startswith("<") and name.endswith(">"):
        return name[1:-1]
    return name


def _breaks_line(value: str) -> bool:
    return len(f"x{value}x".splitlines()) > 1


def check_compose_roundtrip(
    to: Sequence[str],
    subject: str,
    cc: Sequence[str] = (),
    attachment_names: Sequence[str] = (),
) -> None:
    """The raw MIME from ``_compose`` parses back to what was asked for.

    No header injection: the parsed message has only the expected headers, with
    the given Subject, recipients and attachment names. Header values with line
    breaks may be rejected with ValueError (the stdlib's injection guard).
    """
    gmail = Gmail(cast(GoogleAuth, None))
    try:
        api_body = gmail._compose(
            to=list(to),
            subject=subject,
            body="body",
            cc=list(cc) or None,
            attachments=[(name, b"content") for name in attachment_names],
        )
    except ValueError:
        headers = [*to, *cc, subject, *attachment_names]
        if any(_breaks_line(value) for value in headers):
            return
        raise
    try:
        raw = base64.urlsafe_b64decode(api_body["raw"])
    except binascii.Error as exc:
        raise PropertyViolation(f"raw is not base64url: {exc}") from exc
    parsed = email.message_from_bytes(raw, policy=policy.default)
    names = [name.lower() for name in parsed]
    require(len(names) == len(set(names)), f"duplicated headers {names}")
    expected = _COMPOSE_HEADERS if cc else _COMPOSE_HEADERS - {"cc"}
    require(
        expected <= set(names) <= expected | _COMPOSE_HEADERS_OPTIONAL,
        f"headers {names}, expected {sorted(expected)}",
    )
    # Parsers decode anything that looks like an RFC 2047 encoded word, and the
    # stdlib's folding can add or drop whitespace at the ends of the value (a
    # leading space on Python 3.11 when the first token doesn't fit the line;
    # whitespace-only subjects). Neither is the composer's doing.
    if "=?" not in subject:
        got_subject = str(parsed["Subject"])
        require(
            got_subject.strip() == subject.strip(),
            f"Subject {subject!r} came back as {got_subject!r}",
        )
    for header, sent in (("To", to), ("Cc", cc)):
        if sent:
            got = getaddresses([str(parsed[header])])
            want = getaddresses([", ".join(sent)])
            require(got == want, f"{header} {got} != {want}")
    filenames = [part.get_filename() for part in parsed.iter_attachments()]
    require(len(filenames) == len(attachment_names), f"attachments {filenames}")
    for got_name, sent_name in zip(filenames, attachment_names, strict=True):
        require(
            "=?" in sent_name or got_name == _parsed_filename(sent_name),
            f"attachment {sent_name!r} came back as {got_name!r}",
        )


__all__ = [
    "QUERY_OPERATORS",
    "check_compose_roundtrip",
    "check_construct_query_terms",
    "check_html_to_text_plain_passthrough",
    "check_html_to_text_scales",
    "check_html_to_text_strips_tags",
    "check_parse_message",
    "check_query_combinators",
    "check_query_single_term",
    "top_level_terms",
]
