"""Gmail draft."""

from dataclasses import dataclass

from gsuite_gmail.message import Message


@dataclass
class Draft:
    """An unsent message. `message` holds its current content."""

    id: str
    message: Message
