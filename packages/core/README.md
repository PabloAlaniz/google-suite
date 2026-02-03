# gsuite-core

Shared authentication, configuration, and utilities for Google Suite packages.

## Installation

```bash
pip install gsuite-core
```

## Usage

```python
from gsuite_core import GoogleAuth, Settings

# OAuth authentication
auth = GoogleAuth()
credentials = auth.authenticate()  # Opens browser for consent

# Check status
auth.is_authenticated()  # True/False
auth.refresh()           # Refresh expired token

# Service account (for server-to-server)
auth = GoogleAuth.from_service_account("service-account.json")

# Access credentials for Google API clients
from googleapiclient.discovery import build
service = build("gmail", "v1", credentials=auth.credentials)
```

## Scopes

By default, gsuite-core requests scopes for all supported services:

- Gmail: read, send, modify, labels
- Calendar: full access
- Drive: full access (when available)

You can customize scopes:

```python
auth = GoogleAuth(scopes=[
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
])
```

## Token Storage

Tokens are stored locally by default (SQLite). For Cloud Run, use Secret Manager:

```python
from gsuite_core.storage import SecretManagerTokenStore

store = SecretManagerTokenStore(
    project_id="my-project",
    secret_name="gsuite-token",
)
auth = GoogleAuth(token_store=store)
```

## Configuration

Environment variables (prefix `GSUITE_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `GSUITE_CREDENTIALS_FILE` | credentials.json | OAuth credentials |
| `GSUITE_TOKEN_STORAGE` | sqlite | sqlite or secretmanager |
| `GSUITE_TOKEN_DB_PATH` | tokens.db | SQLite path |
| `GSUITE_GCP_PROJECT_ID` | - | For Secret Manager |
