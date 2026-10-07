# gsuite-core

Shared authentication, configuration, and utilities for Google Suite packages.

## Installation

```bash
pip install gsuite-sdk   # gsuite_core ships inside the SDK
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
| `GSUITE_REQUEST_TIMEOUT` | 30 | Seconds before a Google API request times out |
| `GSUITE_MAX_RETRIES` | 3 | Retries per request |
| `GSUITE_RETRY_DELAY` | 1.0 | Base backoff in seconds (exponential, full jitter) |
| `GSUITE_RETRY_ON_RATE_LIMIT` | true | Retry 429 / rate-limit 403 responses |
| `GSUITE_DEFAULT_TIMEZONE` | UTC | Timezone for new events and `Calendar.get_today()` |
| `GSUITE_RATE_LIMIT` | - | Max Google requests per second for the process (sync and async); off by default |
| `GSUITE_RATE_LIMIT_BURST` | max(1, rate) | Token bucket size |

## Retries, errors and pagination

Every Google request made by the clients goes through `gsuite_core.execute()`:

- **Rate limits** (429, or 403 `rateLimitExceeded`) are retried for any
  request, honoring `Retry-After`.
- **Server errors (5xx) and network failures** are retried only for
  idempotent requests (GET, PUT, DELETE). A `POST` that timed out may have
  already sent the email, so it is not repeated.
- Failures raise `gsuite_core.exceptions` types: `NotFoundError`,
  `PermissionDeniedError`, `RateLimitError`, `QuotaExceededError`, or
  `APIError` with the HTTP status. `get_*` methods return `None` for a missing
  resource, and `trash`/`delete`/`share` return `False` for it; every other
  failure raises.

List methods follow result pages: `max_results=None` returns everything, and
the `iter_*` variants (`Gmail.iter_messages`, `Calendar.iter_events`,
`Drive.iter_files`) yield lazily so large mailboxes don't load at once.

The same helpers work for API calls the clients don't wrap:

```python
from gsuite_core import execute, paginate

labels = execute(gmail.service.users().labels().list(userId="me"), "gmail")
for ref in paginate(gmail.service.users().drafts().list, "drafts", "gmail", userId="me"):
    ...
```

## Async

`gsuite_core.aio.AsyncGoogleClient` is the async counterpart (httpx, same
auth, retries, rate limit and errors); see [docs/ASYNC.md](../../docs/ASYNC.md).
