# gsuite-contacts

Simple, Pythonic Google Contacts client over the People API.

## Installation

```bash
pip install gsuite-sdk   # gsuite_contacts ships inside the SDK
```

Enable the **People API** in your Cloud project and log in with the Contacts
scope (a sensitive scope, so it is not in the default login):

```bash
gsuite auth login --force --scopes default,contacts
```

## Quick Start

```python
from gsuite_contacts import Contacts
from gsuite_core import GoogleAuth, Scopes

auth = GoogleAuth(scopes=Scopes.default() + Scopes.contacts())
auth.authenticate()

contacts = Contacts(auth)

for c in contacts.list_contacts(sort_order="FIRST_NAME_ASCENDING"):
    print(c.display_name, c.email, c.phone)

# Prefix search on names, emails, phones and organizations (up to 30 results)
matches = contacts.search("ana")

ana = contacts.create(given_name="Ana", family_name="Pérez", emails=["ana@example.com"])
contacts.update(ana.id, phones=["+54 11 5555-5555"])  # lists replace the old values
contacts.update(ana.id, given_name="Anita")            # keeps the family name
contacts.delete(ana.id)
```

IDs are accepted as `c123` or `people/c123`. Updates send the contact's etag,
so a concurrent change makes the update fail instead of being overwritten.
`get` returns `None` and `delete` returns `False` for a missing contact.
