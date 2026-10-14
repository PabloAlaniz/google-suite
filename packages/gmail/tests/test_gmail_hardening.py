"""Regression tests for hostile input: HTML-to-text, message payloads, query builder."""

import time

import pytest

from gsuite_gmail import query as q
from gsuite_gmail.client import _html_to_text

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
