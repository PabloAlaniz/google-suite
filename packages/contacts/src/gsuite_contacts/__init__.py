"""Google Suite Contacts - Simple People API client."""

__version__ = "0.1.0"

from gsuite_contacts.aio import AsyncContacts
from gsuite_contacts.client import Contacts
from gsuite_contacts.contact import Contact
from gsuite_contacts.group import ContactGroup, ContactsDelta

__all__ = [
    "AsyncContacts",
    "Contact",
    "ContactGroup",
    "Contacts",
    "ContactsDelta",
]
