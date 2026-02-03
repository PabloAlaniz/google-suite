"""Gmail Label entity."""

from dataclasses import dataclass
from enum import StrEnum


class LabelType(StrEnum):
    """Label type classification."""

    SYSTEM = "system"
    USER = "user"


@dataclass
class Label:
    """
    Gmail label.

    Labels are like folders/tags that can be applied to messages.
    """

    id: str
    name: str
    type: LabelType = LabelType.USER
    messages_total: int = 0
    messages_unread: int = 0
    threads_total: int = 0
    threads_unread: int = 0

    @property
    def is_system(self) -> bool:
        """Check if this is a system label."""
        return self.type == LabelType.SYSTEM

    @property
    def has_unread(self) -> bool:
        """Check if label has unread messages."""
        return self.messages_unread > 0


class SystemLabels:
    """Constants for common Gmail system labels."""

    INBOX = "INBOX"
    SENT = "SENT"
    DRAFT = "DRAFT"
    TRASH = "TRASH"
    SPAM = "SPAM"
    STARRED = "STARRED"
    UNREAD = "UNREAD"
    IMPORTANT = "IMPORTANT"
    CATEGORY_PERSONAL = "CATEGORY_PERSONAL"
    CATEGORY_SOCIAL = "CATEGORY_SOCIAL"
    CATEGORY_PROMOTIONS = "CATEGORY_PROMOTIONS"
    CATEGORY_UPDATES = "CATEGORY_UPDATES"
    CATEGORY_FORUMS = "CATEGORY_FORUMS"
