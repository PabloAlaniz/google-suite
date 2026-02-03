"""Gmail Message entity with fluent methods."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from gsuite_gmail.client import Gmail


@dataclass
class Attachment:
    """Email attachment."""

    id: str
    filename: str
    mime_type: str
    size: int
    _message_id: str = ""
    _gmail: Optional["Gmail"] = field(default=None, repr=False)

    def download(self) -> bytes:
        """Download attachment content."""
        if not self._gmail:
            raise RuntimeError("Attachment not linked to Gmail client")
        return self._gmail._download_attachment(self._message_id, self.id)

    def save(self, path: str | None = None) -> str:
        """
        Download and save attachment to disk.

        Args:
            path: Save path (default: current dir with original filename)

        Returns:
            Path where file was saved
        """
        content = self.download()
        save_path = path or self.filename

        with open(save_path, "wb") as f:
            f.write(content)

        return save_path


@dataclass
class Message:
    """
    Gmail message with fluent modification methods.

    Example:
        message.mark_as_read().star().add_label("Work")
    """

    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    date: datetime | None = None
    snippet: str = ""
    plain: str | None = None  # Plain text body
    html: str | None = None  # HTML body
    labels: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    _gmail: Optional["Gmail"] = field(default=None, repr=False)

    @property
    def is_unread(self) -> bool:
        """Check if message is unread."""
        return "UNREAD" in self.labels

    @property
    def is_starred(self) -> bool:
        """Check if message is starred."""
        return "STARRED" in self.labels

    @property
    def is_important(self) -> bool:
        """Check if message is marked important."""
        return "IMPORTANT" in self.labels

    @property
    def body(self) -> str:
        """Get body content (prefers plain text)."""
        return self.plain or self.html or ""

    # Fluent modification methods

    def mark_as_read(self) -> "Message":
        """Mark message as read."""
        if self._gmail and self.is_unread:
            self._gmail._modify_labels(self.id, remove=["UNREAD"])
            self.labels = [l for l in self.labels if l != "UNREAD"]
        return self

    def mark_as_unread(self) -> "Message":
        """Mark message as unread."""
        if self._gmail and not self.is_unread:
            self._gmail._modify_labels(self.id, add=["UNREAD"])
            self.labels.append("UNREAD")
        return self

    def star(self) -> "Message":
        """Star the message."""
        if self._gmail and not self.is_starred:
            self._gmail._modify_labels(self.id, add=["STARRED"])
            self.labels.append("STARRED")
        return self

    def unstar(self) -> "Message":
        """Remove star from message."""
        if self._gmail and self.is_starred:
            self._gmail._modify_labels(self.id, remove=["STARRED"])
            self.labels = [l for l in self.labels if l != "STARRED"]
        return self

    def mark_important(self) -> "Message":
        """Mark message as important."""
        if self._gmail and not self.is_important:
            self._gmail._modify_labels(self.id, add=["IMPORTANT"])
            self.labels.append("IMPORTANT")
        return self

    def mark_not_important(self) -> "Message":
        """Mark message as not important."""
        if self._gmail and self.is_important:
            self._gmail._modify_labels(self.id, remove=["IMPORTANT"])
            self.labels = [l for l in self.labels if l != "IMPORTANT"]
        return self

    def trash(self) -> "Message":
        """Move message to trash."""
        if self._gmail:
            self._gmail._trash_message(self.id)
            if "TRASH" not in self.labels:
                self.labels.append("TRASH")
        return self

    def untrash(self) -> "Message":
        """Remove message from trash."""
        if self._gmail:
            self._gmail._untrash_message(self.id)
            self.labels = [l for l in self.labels if l != "TRASH"]
        return self

    def archive(self) -> "Message":
        """Archive message (remove from inbox)."""
        if self._gmail:
            self._gmail._modify_labels(self.id, remove=["INBOX"])
            self.labels = [l for l in self.labels if l != "INBOX"]
        return self

    def move_to_inbox(self) -> "Message":
        """Move message to inbox."""
        if self._gmail and "INBOX" not in self.labels:
            self._gmail._modify_labels(self.id, add=["INBOX"])
            self.labels.append("INBOX")
        return self

    def add_label(self, label_name: str) -> "Message":
        """Add a label to the message."""
        if self._gmail:
            label_id = self._gmail._get_label_id(label_name)
            if label_id and label_id not in self.labels:
                self._gmail._modify_labels(self.id, add=[label_id])
                self.labels.append(label_id)
        return self

    def remove_label(self, label_name: str) -> "Message":
        """Remove a label from the message."""
        if self._gmail:
            label_id = self._gmail._get_label_id(label_name)
            if label_id and label_id in self.labels:
                self._gmail._modify_labels(self.id, remove=[label_id])
                self.labels = [l for l in self.labels if l != label_id]
        return self

    def reply(
        self,
        body: str,
        html: bool = False,
        signature: bool = False,
    ) -> "Message":
        """
        Reply to this message.

        Args:
            body: Reply body
            html: Whether body is HTML
            signature: Include account signature

        Returns:
            The sent reply message
        """
        if not self._gmail:
            raise RuntimeError("Message not linked to Gmail client")

        return self._gmail.send(
            to=[self.sender],
            subject=f"Re: {self.subject}" if not self.subject.startswith("Re:") else self.subject,
            body=body,
            html=html,
            signature=signature,
            reply_to=self.id,
            thread_id=self.thread_id,
        )
