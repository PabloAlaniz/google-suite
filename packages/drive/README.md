# gsuite-drive

Simple, Pythonic Google Drive API client.

## Installation

```bash
pip install gsuite-drive
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
file = drive.get("file_id")
file.download("/path/to/save/file.pdf")

# Download with automatic naming
file.download("/path/to/save/")  # Uses original filename

# Download Google Docs as different formats
doc = drive.get("google_doc_id")
doc.download("document.docx", export_format="docx")
doc.download("document.pdf", export_format="pdf")

# Export formats for Google Docs:
# - document: docx, odt, pdf, txt, html, rtf, epub
# - spreadsheet: xlsx, ods, pdf, csv, tsv
# - presentation: pptx, odp, pdf, txt
# - drawing: png, pdf, jpg, svg

# Download to memory
content = file.download_bytes()
```

## Uploading Files

```python
# Upload a file
uploaded = drive.upload("local_file.pdf")
print(f"Uploaded: {uploaded.id}")
print(f"Link: {uploaded.web_view_link}")

# Upload to specific folder
uploaded = drive.upload(
    "report.pdf",
    parent_id="folder_id_here",
)

# Upload with custom name
uploaded = drive.upload(
    "local_name.pdf",
    name="Public Report Q1 2026.pdf",
)

# Upload from bytes
content = b"Hello, World!"
uploaded = drive.upload_bytes(
    content,
    name="hello.txt",
    mime_type="text/plain",
)

# Upload and convert to Google Docs format
uploaded = drive.upload(
    "document.docx",
    convert=True,  # Converts to Google Docs
)
```

## Creating Folders

```python
# Create folder in root
folder = drive.create_folder("My New Folder")

# Create nested folder
parent = drive.create_folder("Projects")
subfolder = drive.create_folder("Project A", parent_id=parent.id)

# Upload to new folder
folder = drive.create_folder("Reports 2026")
drive.upload("q1_report.pdf", parent_id=folder.id)
```

## Moving and Copying

```python
# Move file to folder
drive.move("file_id", to_folder_id="new_folder_id")

# Copy file
copy = drive.copy("file_id")
copy = drive.copy("file_id", name="Copy of Document")

# Rename file
drive.rename("file_id", "New Name.pdf")
```

## Deleting Files

```python
# Move to trash
drive.trash("file_id")

# Restore from trash
drive.untrash("file_id")

# Permanently delete (careful!)
drive.delete("file_id")

# Empty trash
drive.empty_trash()
```

## Sharing

```python
# Share with specific user
drive.share(
    "file_id",
    email="user@example.com",
    role="reader",  # reader, writer, commenter
)

# Share with anyone who has link
drive.share(
    "file_id",
    anyone=True,
    role="reader",
)

# Get sharing permissions
permissions = drive.get_permissions("file_id")
for perm in permissions:
    print(f"{perm.email}: {perm.role}")

# Remove sharing
drive.unshare("file_id", permission_id="permission_id")
```

## Searching

```python
# Search by name
files = drive.search("quarterly report")

# Full-text search (searches content)
files = drive.search("budget projections", full_text=True)

# Advanced query
files = drive.list_files(
    query="name contains 'report' and mimeType='application/pdf' and modifiedTime > '2026-01-01'"
)
```

## Folder Operations

```python
# Get folder contents
folder = drive.get_folder("folder_id")
for item in folder.list_children():
    print(f"{'📁' if item.is_folder else '📄'} {item.name}")

# Get folder tree
tree = drive.get_folder_tree("folder_id", max_depth=3)
```

## Watching for Changes

```python
# Get changes since last check
changes = drive.get_changes(start_page_token="token")
for change in changes:
    if change.removed:
        print(f"Removed: {change.file_id}")
    else:
        print(f"Modified: {change.file.name}")

# Get initial page token
token = drive.get_start_page_token()
```

## Error Handling

```python
from gsuite_core.exceptions import (
    GsuiteError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
)

try:
    file = drive.get("nonexistent_id")
except NotFoundError:
    print("File not found")
except PermissionDeniedError:
    print("No access to this file")
except QuotaExceededError:
    print("Storage quota exceeded")
except GsuiteError as e:
    print(f"Drive error: {e}")
```

## Configuration

Uses `gsuite-core` settings. See [gsuite-core README](../core/README.md) for auth configuration.

## License

MIT
