"""Google Suite Contacts - Simple People API client."""

__version__ = "0.1.0"

from gsuite_contacts.client import Contacts
from gsuite_contacts.contact import Contact

__all__ = [
    "Contacts",
    "Contact",
]
