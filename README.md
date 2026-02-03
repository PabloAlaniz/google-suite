# Google Suite

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Unified Python SDK for Google Workspace APIs with Clean Architecture.

## Features

- 🔐 **Unified Auth** - Single OAuth flow for all Google APIs
- 📧 **Gmail** - Send, receive, search, labels, attachments
- 📅 **Calendar** - Events, calendars, scheduling
- 📁 **Drive** - Files, folders, sharing, upload/download
- 📊 **Sheets** - Read, write, append, format, batch operations
- 🚀 **REST API** - Single FastAPI gateway for all services
- 💻 **CLI** - Unified command-line interface

## Installation

```bash
pip install gsuite-sdk
```

Optional extras:
```bash
pip install gsuite-sdk[cloudrun]  # Google Cloud Secret Manager support
pip install gsuite-sdk[all]       # All optional dependencies (FastAPI, CLI)
```

## Quick Start

### Prerequisites

You need OAuth credentials from Google Cloud Console. See [Getting Credentials](docs/GETTING_CREDENTIALS.md) for a step-by-step guide.

### Authentication

```python
from gsuite_core import GoogleAuth

# OAuth (interactive, opens browser)
auth = GoogleAuth()
auth.authenticate()

# Or with service account
auth = GoogleAuth.from_service_account("service-account.json")
```

### Gmail

```python
from gsuite_gmail import Gmail, query

gmail = Gmail(auth)

# Get unread messages with fluent API
for message in gmail.get_unread():
    print(f"{message.sender}: {message.subject}")
    message.mark_as_read().archive()  # Fluent chaining!

# Send email with signature
gmail.send(
    to=["recipient@example.com"],
    subject="Hello",
    body="World",
    signature=True,  # Appends your Gmail signature
)

# Search with query builder (inspired by simplegmail)
messages = gmail.search(
    query.newer_than(days=7) & query.has_attachment() & query.from_("boss@company.com")
)

# Or use construct_query for dict-style
messages = gmail.search(query.construct_query(
    unread=True,
    newer_than=(7, "day"),
    labels=["Work"],
))
```

### Drive

```python
from gsuite_drive import Drive

drive = Drive(auth)

# List files
for file in drive.list_files():
    print(f"{file.name} ({file.mime_type})")

# Upload
uploaded = drive.upload("document.pdf")
print(f"Uploaded: {uploaded.web_view_link}")

# Download
file = drive.get("file_id")
file.download("local_copy.pdf")

# Create folder and upload into it
folder = drive.create_folder("My Folder")
drive.upload("file.txt", parent_id=folder.id)
```

### Calendar

```python
from gsuite_calendar import Calendar

calendar = Calendar(auth)

# Get upcoming events
events = calendar.get_upcoming(days=7)
for event in events:
    print(f"{event.start}: {event.summary}")

# Create event
calendar.create_event(
    summary="Meeting",
    start="2026-01-30T10:00:00",
    end="2026-01-30T11:00:00",
)
```

### REST API

```bash
# Start unified API server
gsuite serve --port 8080

# Or with Docker
docker run -p 8080:8080 gsuite-api
```

```bash
# All services under one roof
curl http://localhost:8080/gmail/messages/unread
curl http://localhost:8080/calendar/events/upcoming
curl http://localhost:8080/drive/files
```

**Interactive API docs available at `/docs` when server is running.** See [API Documentation](#api-documentation) section below for details.

### CLI

```bash
# Authentication
gsuite auth login              # Opens browser for OAuth
gsuite auth status             # Check auth status
gsuite auth export             # Export token for Cloud Run

# Gmail
gsuite gmail list --unread     # List unread messages
gsuite gmail read MSG_ID       # Read specific message
gsuite gmail send --to user@example.com --subject "Hi" --body "Hello"
gsuite gmail search "from:boss has:attachment"
gsuite gmail labels            # List all labels

# Calendar  
gsuite calendar list --days 7  # Upcoming events
gsuite calendar today          # Today's events
gsuite calendar week           # Week view
gsuite calendar create "Meeting" --start "2026-01-30 10:00"
gsuite calendar calendars      # List calendars

# Server
gsuite serve --port 8080       # Start REST API
gsuite status                  # Overall status
```

## Architecture

```
google-suite/
├── packages/
│   ├── core/           # Shared auth, config, token storage
│   ├── gmail/          # Gmail client + query builder
│   ├── calendar/       # Calendar client
│   ├── drive/          # Drive client (upload, download, share)
│   └── sheets/         # Sheets client (planned)
├── api/                # Unified FastAPI REST gateway
├── cli/                # Unified CLI (Typer + Rich)
├── skill/              # AI agent skill (OpenClaw compatible)
└── tests/              # Integration tests
```

### Design Principles

- **Clean Architecture** - Domain entities, interfaces, infrastructure separation
- **Provider Agnostic** - Swap implementations via interfaces
- **Shared Auth** - One OAuth flow grants access to all services
- **Independent Packages** - Install only what you need
- **Unified Gateway** - Single API/CLI for all services

## AI Agent Skill

This repo includes an [OpenClaw](https://openclaw.ai)-compatible skill for AI agents:

```
skill/
├── SKILL.md      # Usage documentation for agents
└── skill.json    # Skill metadata
```

Agents can use this skill to interact with Google Workspace on behalf of users.

## Standalone Repos

This monorepo consolidates and extends these standalone projects:

- [Gmail-API](https://github.com/PabloAlaniz/Gmail-API) - Standalone Gmail API
- [Calendar-API](https://github.com/PabloAlaniz/Calendar-API) - Standalone Calendar API

The standalone repos remain functional for existing deployments.

## Configuration

Environment variables (prefix `GSUITE_`):

| Variable | Description |
|----------|-------------|
| `GSUITE_CREDENTIALS_FILE` | OAuth credentials JSON path |
| `GSUITE_TOKEN_STORAGE` | `sqlite` or `secretmanager` |
| `GSUITE_TOKEN_DB_PATH` | SQLite token database path |
| `GSUITE_GCP_PROJECT_ID` | GCP project (for Secret Manager) |
| `GSUITE_API_KEY` | API key for REST endpoints |

## Development

```bash
# Clone
git clone https://github.com/PabloAlaniz/google-suite.git
cd google-suite

# Install all packages in dev mode
pip install -e "packages/core[dev]"
pip install -e "packages/gmail[dev]"
pip install -e "packages/calendar[dev]"
pip install -e "api[dev]"
pip install -e "cli[dev]"

# Run tests
pytest

# Lint
ruff check packages api cli
```

## Deployment

### Cloud Run (GCP)

Deploy the REST API to Cloud Run with Secret Manager for token storage:

```bash
# Build and push Docker image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/gsuite-api

# Deploy to Cloud Run
gcloud run deploy gsuite-api \
  --image gcr.io/YOUR_PROJECT/gsuite-api \
  --platform managed \
  --region us-central1 \
  --set-env-vars GSUITE_TOKEN_STORAGE=secretmanager \
  --set-env-vars GSUITE_GCP_PROJECT_ID=YOUR_PROJECT \
  --allow-unauthenticated  # or use --no-allow-unauthenticated + IAM
```

**Note:** For Secret Manager token storage, ensure your Cloud Run service account has `secretmanager.versions.access` permission.

### Docker Compose

For local development or self-hosted deployment:

```yaml
version: '3.8'
services:
  gsuite-api:
    build: .
    ports:
      - "8080:8080"
    environment:
      GSUITE_CREDENTIALS_FILE: /secrets/credentials.json
      GSUITE_TOKEN_DB_PATH: /data/tokens.db
      GSUITE_API_KEY: your-api-key-here
    volumes:
      - ./credentials.json:/secrets/credentials.json:ro
      - ./data:/data
```

## API Documentation

When running the REST API server, interactive API docs are available at:

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`

## Troubleshooting

### Token refresh failed

**Problem:** `TokenRefreshError: Failed to refresh token`

**Solution:**
- Delete the token database: `rm ~/.gsuite/tokens.db` (or your configured path)
- Re-authenticate: `gsuite auth login`
- For service accounts, verify the JSON file hasn't expired

### Missing scopes

**Problem:** `HttpError 403: Insufficient Permission`

**Solution:**
- Check required scopes in error message
- Re-authenticate with additional scopes:
  ```bash
  gsuite auth login --scopes gmail.readonly,calendar,drive
  ```
- Or update `GSUITE_DEFAULT_SCOPES` environment variable

### Credentials not found

**Problem:** `CredentialsNotFoundError: OAuth credentials file not found`

**Solution:**
- Download OAuth credentials from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- Save as `credentials.json` in working directory
- Or set `GSUITE_CREDENTIALS_FILE` environment variable

### Import errors

**Problem:** `ModuleNotFoundError: No module named 'gsuite_gmail'`

**Solution:**
- Install the package: `pip install gsuite-gmail`
- Or for development: `pip install -e "packages/gmail[dev]"`

## License

MIT - see [LICENSE](LICENSE)

## Author

Pablo Alaniz ([@PabloAlaniz](https://github.com/PabloAlaniz))
