"""Google Suite Gmail - Simple Gmail API client."""

__version__ = "0.1.0"

from gsuite_gmail import query
from gsuite_gmail.client import Gmail
from gsuite_gmail.label import Label
from gsuite_gmail.message import Message
from gsuite_gmail.thread import Thread

__all__ = [
    "Gmail",
    "Message",
    "Thread",
    "Label",
    "query",
]
