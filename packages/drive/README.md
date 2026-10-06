# gsuite-drive

Simple, Pythonic Google Drive API client.

## Installation

```bash
pip install gsuite-sdk   # gsuite_drive ships inside the SDK
```

## Quick Start

```python
from gsuite_core import GoogleAuth
from gsuite_drive import Drive

# Authenticate
auth = GoogleAuth()
auth.authenticate()  # Opens browser for consent

drive = Drive(auth)
```

## Listing Files

```python
# List recent files
for file in drive.list_files(max_results=20):
    print(f"{file.name} ({file.mime_type})")
    print(f"  Modified: {file.modified_time}")
    print(f"  Size: {file.size_human}")

# List files in a specific folder
files = drive.list_files(parent_id="folder_id_here")

# Filter by type
docs = drive.list_files(mime_type="application/vnd.google-apps.document")
pdfs = drive.list_files(mime_type="application/pdf")
folders = drive.list_files(mime_type="application/vnd.google-apps.folder")

# Custom query
files = drive.list_files(query="name contains 'report'")
files = drive.list_files(query="modifiedTime > '2026-01-01'")
```

## File Properties

```python
file = drive.get("file_id")

# Basic info
file.id           # File ID
file.name         # Filename
file.mime_type    # MIME type
file.size         # Size in bytes
file.size_human   # "1.5 MB"

# Times
file.created_time   # datetime
file.modified_time  # datetime

# Location
file.parents        # List of parent folder IDs
file.path           # Full path (if available)

# Sharing
file.shared         # bool
file.web_view_link  # Link to view in browser
file.web_content_link # Direct download link

# Ownership
file.owners         # List of owners
file.is_owned_by_me # bool
```

## Downloading Files

```python
# Download by ID
file = drive.get("file_id")          # None if it doesn't exist
file.download("/path/to/file.pdf")
file.download()                      # current dir, original name

# Content in memory
content = drive.get_content("file_id")

# Google Docs/Sheets/Slides can't be downloaded as-is; they are exported.
# file.download() picks docx/xlsx/pptx unless you choose a format.
doc = drive.get("google_doc_id")
doc.download()                            # "Name.docx"
doc.download("report.pdf", export_format="pdf")
pdf_bytes = drive.export("google_doc_id", "pdf")

# Formats: pdf, docx, xlsx, pptx, odt, ods, odp, rtf, txt, md, html,
# epub, csv, tsv, png, jpeg, svg (see gsuite_drive.EXPORT_FORMATS)
# or any MIME type Drive supports. Drive caps exports at 10 MB.
```

## Uploading Files

Uploads are resumable and sent in chunks; a failed chunk is retried from
the last byte Drive acknowledged, so a retry can't duplicate the file.

```python
uploaded = drive.upload("local_file.pdf")
print(uploaded.id, uploaded.web_view_link)

# To a folder, with another name
drive.upload("report.pdf", parent_id="folder_id", name="Q1 Report.pdf")

# From bytes or a file-like object
drive.upload_content(b"Hello, World!", name="hello.txt", mime_type="text/plain")

# Progress (fraction 0.0-1.0)
drive.upload("big.zip", on_progress=lambda done: print(f"{done:.0%}"))
```

## Creating Folders

```python
folder = drive.create_folder("Projects")
subfolder = drive.create_folder("Project A", parent_id=folder.id)
drive.upload("q1_report.pdf", parent_id=subfolder.id)
```

## Updating, Moving and Copying

```python
drive.rename("file_id", "New Name.pdf")
drive.update("file_id", description="Final version", starred=True)

drive.move("file_id", "new_folder_id")       # leaves its old folders
copy = drive.copy("file_id", name="Copy of Document", parent_id="folder_id")
```

## Deleting Files

```python
drive.trash("file_id")       # True, or False if the file doesn't exist
drive.restore("file_id")     # back from the trash
drive.delete("file_id")      # permanent, careful

# What's in the trash
for f in drive.list_files(trashed=True):
    print(f.name)
```

Any failure other than "not found" (permissions, auth, rate limits) raises.

## Sharing

```python
# With a user (emails them by default)
drive.share("file_id", "user@example.com", role="writer")

# Anyone with the link, a whole domain, or a group
drive.add_permission("file_id", type="anyone", role="reader")
drive.add_permission("file_id", type="domain", domain="example.com")
drive.add_permission("file_id", type="group", email="team@example.com", notify=False)

# Who has access, and revoking it
for perm in drive.list_permissions("file_id"):
    print(perm.id, perm.role, perm.email_address or perm.domain or perm.type)
drive.remove_permission("file_id", "permission_id")
```

## Searching

```python
# By name (quotes in the name are escaped for you)
files = drive.search("quarterly report")
files = drive.search("Pablo's notes.txt", exact=True)

# Raw Drive query; quote values with drive_query_literal
from gsuite_core import drive_query_literal

files = drive.list_files(
    query=f"fullText contains {drive_query_literal('budget')} and modifiedTime > '2026-01-01'"
)

# Everything, page after page (max_results=None), lazily
for f in drive.iter_files(mime_type="application/pdf", max_results=None):
    ...
```

Listings include shared drives.

## Folder Operations

```python
folders = drive.list_folders(parent_id="folder_id")

folder = folders[0]
folder.list_files()                 # direct children
folder.list_files(recursive=True)   # whole tree, breadth-first
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GSuiteError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

try:
    drive.move("file_id", "folder_id")
except NotFoundError:
    print("File not found")
except PermissionDeniedError:
    print("No access, or the Drive is full")
except RateLimitError:
    print("Still rate limited after retries")
except GSuiteError as e:
    print(f"Drive error: {e}")
```

`get()` returns `None` for a missing file instead of raising.

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
