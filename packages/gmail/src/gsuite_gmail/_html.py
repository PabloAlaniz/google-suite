"""Plain-text rendering of HTML mail bodies, in linear time.

The HTML comes from other people's messages when replying or forwarding, so
none of these functions may backtrack: every regex runs over each input
character a bounded number of times.
"""

import html as html_lib
import re

_RAW_TEXT_OPEN = re.compile(r"(?i)<(script|style)")
_RAW_TEXT_CLOSE = {
    "script": re.compile(r"(?i)</script>"),
    "style": re.compile(r"(?i)</style>"),
}
_LINE_BREAK = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>")
_TAG = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n{3,}")
_DECIMAL_CHARREF = re.compile(r"&#(\d+)")
# Anything past 7 digits is above U+10FFFF, which unescape turns into U+FFFD
_MAX_CHARREF_DIGITS = 7


def _strip_raw_text_elements(markup: str) -> str:
    """Drop ``<script ... </script>`` and ``<style ... </style>`` blocks in linear time.

    Same result as ``re.sub(r"(?is)<(script|style).*?</\\1>", "", markup)``, which
    rescans to the end of the input for every opener without a closer. A closer
    missing after one opener is missing after every later one too, so each
    element name is searched to the end at most once.
    """
    out: list[str] = []
    pos = 0
    unclosed: set[str] = set()
    for opener in _RAW_TEXT_OPEN.finditer(markup):
        # Index 1 tells them apart ("sc" / "st"); .lower() would not be safe
        # for Unicode case-insensitive matches such as the long s.
        name = "style" if opener.group(1)[1] in "tT" else "script"
        if opener.start() < pos or name in unclosed:
            continue
        closer = _RAW_TEXT_CLOSE[name].search(markup, opener.end())
        if closer is None:
            unclosed.add(name)
            continue
        out.append(markup[pos : opener.start()])
        pos = closer.end()
    out.append(markup[pos:])
    return "".join(out)


def _strip_tags(text: str) -> str:
    """``re.sub(r"<[^>]+>", "", text)`` in linear time.

    The bare regex rescans to the end for every ``<`` with no ``>`` after it.
    Nothing after the last ``>`` can match; before it, every attempt either
    matches up to the next ``>`` (consuming the span) or fails at once on ``<>``.
    """
    last = text.rfind(">")
    return _TAG.sub("", text[: last + 1]) + text[last + 1 :]


def _shorten_charref(match: re.Match[str]) -> str:
    digits = match.group(1).lstrip("0") or "0"
    return f"&#{digits if len(digits) <= _MAX_CHARREF_DIGITS else 65533}"


def _unescape(text: str) -> str:
    """``html.unescape`` that accepts decimal references of any length.

    The stdlib converts the digits with ``int()``, which raises ValueError past
    4300 digits (``sys.int_info.str_digits_check_threshold``), even for
    ``&#000...060;``. Shortening them first gives the same result.
    """
    return html_lib.unescape(_DECIMAL_CHARREF.sub(_shorten_charref, text))


def html_to_text(markup: str) -> str:
    """Rough plain-text version of HTML, for the text/plain alternative."""
    text = _strip_raw_text_elements(markup)
    text = _LINE_BREAK.sub("\n", text)
    text = _strip_tags(text)
    return _unescape(_BLANK_LINES.sub("\n\n", text)).strip()
