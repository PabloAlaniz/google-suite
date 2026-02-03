"""Gmail Thread entity."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gsuite_gmail.message import Message


@dataclass
class Thread:
    """
    Gmail thread (conversation).

    A thread is a collection of related messages.
    """

    id: str
    messages: list["Message"] = field(default_factory=list)
    snippet: str = ""

    @property
    def subject(self) -> str:
        """Get thread subject from first message."""
        if self.messages:
            return self.messages[0].subject
        return ""

    @property
    def message_count(self) -> int:
        """Get number of messages in thread."""
        return len(self.messages)

    @property
    def participants(self) -> set[str]:
        """Get all unique email addresses in thread."""
        emails = set()
        for msg in self.messages:
            emails.add(msg.sender)
            emails.add(msg.recipient)
        return emails

    @property
    def has_unread(self) -> bool:
        """Check if thread has any unread messages."""
        return any(msg.is_unread for msg in self.messages)

    @property
    def labels(self) -> set[str]:
        """Get all unique labels from all messages."""
        all_labels = set()
        for msg in self.messages:
            all_labels.update(msg.labels)
        return all_labels
