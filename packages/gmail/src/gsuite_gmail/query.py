"""Gmail query builder for intuitive searches."""

from dataclasses import dataclass


@dataclass
class Query:
    """
    Gmail search query builder.

    Supports combining queries with & (AND) and | (OR).

    Example:
        q = newer_than(days=7) & has_attachment() & from_("boss@company.com")
        messages = gmail.search(q)
    """

    _query: str

    def __str__(self) -> str:
        return self._query

    def __and__(self, other: "Query") -> "Query":
        """Combine with AND."""
        return Query(f"{self._query} {other._query}")

    def __or__(self, other: "Query") -> "Query":
        """Combine with OR."""
        return Query(f"({self._query}) OR ({other._query})")

    def __invert__(self) -> "Query":
        """Negate query."""
        return Query(f"-({self._query})")


def from_(address: str) -> Query:
    """Messages from a specific sender."""
    return Query(f"from:{address}")


def to(address: str) -> Query:
    """Messages to a specific recipient."""
    return Query(f"to:{address}")


def subject(text: str) -> Query:
    """Messages with subject containing text."""
    if " " in text:
        return Query(f'subject:"{text}"')
    return Query(f"subject:{text}")


def has_words(words: str) -> Query:
    """Messages containing specific words."""
    return Query(words)


def has_attachment() -> Query:
    """Messages with attachments."""
    return Query("has:attachment")


def is_unread() -> Query:
    """Unread messages."""
    return Query("is:unread")


def is_read() -> Query:
    """Read messages."""
    return Query("is:read")


def is_starred() -> Query:
    """Starred messages."""
    return Query("is:starred")


def is_important() -> Query:
    """Important messages."""
    return Query("is:important")


def in_inbox() -> Query:
    """Messages in inbox."""
    return Query("in:inbox")


def in_sent() -> Query:
    """Sent messages."""
    return Query("in:sent")


def in_drafts() -> Query:
    """Draft messages."""
    return Query("in:drafts")


def in_trash() -> Query:
    """Trashed messages."""
    return Query("in:trash")


def in_spam() -> Query:
    """Spam messages."""
    return Query("in:spam")


def label(name: str) -> Query:
    """Messages with a specific label."""
    if " " in name:
        return Query(f'label:"{name}"')
    return Query(f"label:{name}")


def newer_than(days: int | None = None, months: int | None = None) -> Query:
    """Messages newer than a time period."""
    if days:
        return Query(f"newer_than:{days}d")
    if months:
        return Query(f"newer_than:{months}m")
    raise ValueError("Specify days or months")


def older_than(days: int | None = None, months: int | None = None) -> Query:
    """Messages older than a time period."""
    if days:
        return Query(f"older_than:{days}d")
    if months:
        return Query(f"older_than:{months}m")
    raise ValueError("Specify days or months")


def after(date: str) -> Query:
    """Messages after a date (YYYY/MM/DD)."""
    return Query(f"after:{date}")


def before(date: str) -> Query:
    """Messages before a date (YYYY/MM/DD)."""
    return Query(f"before:{date}")


def filename(name: str) -> Query:
    """Messages with attachment matching filename."""
    return Query(f"filename:{name}")


def size_larger(bytes: int) -> Query:
    """Messages larger than size in bytes."""
    return Query(f"larger:{bytes}")


def size_smaller(bytes: int) -> Query:
    """Messages smaller than size in bytes."""
    return Query(f"smaller:{bytes}")


def category(name: str) -> Query:
    """Messages in a category (primary, social, promotions, updates, forums)."""
    return Query(f"category:{name}")


def raw(query_string: str) -> Query:
    """Raw Gmail query string."""
    return Query(query_string)


# Convenience function to build query from dict (like simplegmail)
def construct_query(
    from_: str | None = None,
    to: str | None = None,
    subject: str | None = None,
    unread: bool | None = None,
    starred: bool | None = None,
    newer_than: tuple[int, str] | None = None,  # (2, "day")
    older_than: tuple[int, str] | None = None,
    labels: list[str] | None = None,
    has_attachment: bool | None = None,
    exclude_starred: bool | None = None,
) -> Query:
    """
    Build query from parameters.

    Args:
        from_: Sender email
        to: Recipient email
        subject: Subject contains
        unread: True for unread only
        starred: True for starred only
        newer_than: Tuple of (amount, unit) e.g., (2, "day")
        older_than: Tuple of (amount, unit)
        labels: List of label names
        has_attachment: True for messages with attachments
        exclude_starred: True to exclude starred

    Returns:
        Query object
    """
    parts = []

    if from_:
        parts.append(f"from:{from_}")
    if to:
        parts.append(f"to:{to}")
    if subject:
        parts.append(f'subject:"{subject}"' if " " in subject else f"subject:{subject}")
    if unread:
        parts.append("is:unread")
    if starred:
        parts.append("is:starred")
    if exclude_starred:
        parts.append("-is:starred")
    if newer_than:
        amount, unit = newer_than
        unit_map = {"day": "d", "days": "d", "d": "d", "month": "m", "months": "m", "m": "m"}
        parts.append(f"newer_than:{amount}{unit_map.get(unit, unit)}")
    if older_than:
        amount, unit = older_than
        unit_map = {"day": "d", "days": "d", "d": "d", "month": "m", "months": "m", "m": "m"}
        parts.append(f"older_than:{amount}{unit_map.get(unit, unit)}")
    if labels:
        for lbl in labels:
            parts.append(f'label:"{lbl}"' if " " in lbl else f"label:{lbl}")
    if has_attachment:
        parts.append("has:attachment")

    return Query(" ".join(parts))
