# gsuite-gmail

Simple, Pythonic Gmail API client.

## Installation

```bash
pip install gsuite-gmail
```

## Quick Start

```python
from gsuite_core import GoogleAuth
from gsuite_gmail import Gmail, query

# Authenticate
auth = GoogleAuth()
auth.authenticate()  # Opens browser for consent

gmail = Gmail(auth)
```

## Reading Messages

```python
# Get unread messages
for msg in gmail.get_unread(max_results=10):
    print(f"From: {msg.sender}")
    print(f"Subject: {msg.subject}")
    print(f"Date: {msg.date}")
    print(f"Body: {msg.body[:200]}...")

# Get starred messages
for msg in gmail.get_starred():
    print(msg.subject)

# Get all messages with pagination
messages = gmail.get_messages(max_results=50)
```

## Searching with Query Builder

Fluent API for building Gmail search queries:

```python
from gsuite_gmail import query

# Simple queries
messages = gmail.search(query.from_("boss@company.com"))
messages = gmail.search(query.is_unread())
messages = gmail.search(query.has_attachment())

# Combine with & (AND) and | (OR)
messages = gmail.search(
    query.newer_than(days=7) & 
    query.has_attachment() & 
    query.from_("important@company.com")
)

# Negation with ~
messages = gmail.search(~query.is_starred())

# Complex example
messages = gmail.search(
    (query.from_("team@company.com") | query.from_("boss@company.com")) &
    query.newer_than(days=30) &
    ~query.label("Processed")
)
```

### Query Functions

| Function | Example | Gmail Query |
|----------|---------|-------------|
| `from_(email)` | `query.from_("user@example.com")` | `from:user@example.com` |
| `to(email)` | `query.to("me@example.com")` | `to:me@example.com` |
| `subject(text)` | `query.subject("meeting")` | `subject:meeting` |
| `is_unread()` | `query.is_unread()` | `is:unread` |
| `is_starred()` | `query.is_starred()` | `is:starred` |
| `has_attachment()` | `query.has_attachment()` | `has:attachment` |
| `newer_than(days=N)` | `query.newer_than(days=7)` | `newer_than:7d` |
| `older_than(days=N)` | `query.older_than(days=30)` | `older_than:30d` |
| `label(name)` | `query.label("Work")` | `label:Work` |
| `in_inbox()` | `query.in_inbox()` | `in:inbox` |
| `raw(query)` | `query.raw("filename:pdf")` | `filename:pdf` |

### Dict-style Query (simplegmail compatible)

```python
from gsuite_gmail.query import construct_query

# Same API as simplegmail
messages = gmail.search(construct_query(
    unread=True,
    sender="notifications@github.com",
    newer_than=(7, "day"),
    labels=["GitHub"],
))
```

## Sending Email

```python
# Simple send
gmail.send(
    to=["recipient@example.com"],
    subject="Hello!",
    body="This is the message body.",
)

# With CC, BCC, and HTML
gmail.send(
    to=["main@example.com"],
    cc=["copy@example.com"],
    bcc=["hidden@example.com"],
    subject="Meeting Notes",
    body="<h1>Notes</h1><p>HTML content here</p>",
    html=True,
)

# With attachments
gmail.send(
    to=["user@example.com"],
    subject="Report",
    body="Please find attached.",
    attachments=["report.pdf", "data.xlsx"],
)

# Reply to a message
original = gmail.get_messages(max_results=1)[0]
gmail.reply(
    message=original,
    body="Thanks for your email!",
)

# Forward a message
gmail.forward(
    message=original,
    to=["colleague@example.com"],
    body="FYI - see below",
)
```

## Message Actions

```python
msg = gmail.get_messages(max_results=1)[0]

# Mark as read/unread
msg.mark_as_read()
msg.mark_as_unread()

# Star/unstar
msg.star()
msg.unstar()

# Archive (remove from inbox)
msg.archive()

# Move to trash
msg.trash()

# Add/remove labels
msg.add_label("Important")
msg.remove_label("Unprocessed")

# Fluent chaining
msg.mark_as_read().archive().add_label("Processed")
```

## Labels

```python
# List all labels
for label in gmail.get_labels():
    print(f"{label.name} ({label.type})")

# Get messages with specific label
messages = gmail.get_messages(labels=["IMPORTANT"])

# Create label
gmail.create_label("My Custom Label")

# Delete label
gmail.delete_label("label_id")
```

## Attachments

```python
msg = gmail.get_messages(query=query.has_attachment())[0]

for attachment in msg.attachments:
    print(f"Name: {attachment.filename}")
    print(f"Size: {attachment.size} bytes")
    print(f"Type: {attachment.mime_type}")
    
    # Download
    attachment.download(f"/tmp/{attachment.filename}")
```

## Thread Operations

```python
# Get threads instead of messages
threads = gmail.get_threads(max_results=10)

for thread in threads:
    print(f"Thread ID: {thread.id}")
    print(f"Messages: {thread.message_count}")
    
    # Get all messages in thread
    for msg in thread.messages:
        print(f"  - {msg.subject}")
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GsuiteError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
)

try:
    gmail.send(to=["user@example.com"], subject="Hi", body="Hello")
except RateLimitError:
    print("Hit rate limit, waiting...")
    time.sleep(60)
except AuthenticationError:
    print("Need to re-authenticate")
except GsuiteError as e:
    print(f"Gmail error: {e}")
```

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
