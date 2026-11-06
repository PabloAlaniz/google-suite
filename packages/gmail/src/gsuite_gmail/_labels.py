"""Label names to IDs, with the user's label list cached until it changes."""

from collections.abc import Callable, Sequence
from typing import Any

from gsuite_core.exceptions import ValidationError

# Fixed IDs that work without looking them up
SYSTEM_LABELS = frozenset(
    {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH", "CHAT"}
)


class LabelResolver:
    """Resolve label names (or IDs) to IDs.

    Args:
        list_labels: Returns the user's labels as the API lists them
            (``{"id", "name", ...}`` dicts). Called once, then again only after
            :meth:`invalidate`.
    """

    def __init__(self, list_labels: Callable[[], list[dict[str, Any]]]) -> None:
        self._list_labels = list_labels
        self._by_name: dict[str, str] | None = None

    @property
    def cached(self) -> bool:
        """Whether the label list is loaded."""
        return self._by_name is not None

    def invalidate(self) -> None:
        """Forget the cached list; call after creating, renaming or deleting a label."""
        self._by_name = None

    def resolve(self, name: str) -> str | None:
        """The label's ID, or None if there is no such label. IDs pass through."""
        if name in SYSTEM_LABELS or name.startswith("CATEGORY_"):
            return name
        if self._by_name is None:
            self._by_name = {label["name"]: label["id"] for label in self._list_labels()}
        if name in self._by_name.values():
            return name
        return self._by_name.get(name)

    def require(self, names: Sequence[str]) -> list[str]:
        """IDs for every name; ValidationError on the first unknown one."""
        ids = []
        for name in names:
            label_id = self.resolve(name)
            if label_id is None:
                raise ValidationError("labels", f"unknown label {name!r}")
            ids.append(label_id)
        return ids
