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

Or keep them in the operating system's keyring (Keychain, Credential Manager,
Secret Service), encrypted at rest. It needs `gsuite-sdk[keyring]` and a
desktop session; servers and containers usually have no keyring:

```python
from gsuite_core import KeyringTokenStore

auth = GoogleAuth(token_store=KeyringTokenStore())   # or GSUITE_TOKEN_STORAGE=keyring
```

`GoogleAuth()` without a `token_store` uses the backend that
`GSUITE_TOKEN_STORAGE` selects (`create_token_store()` builds it).

## Accounts

A token store holds several logins, each under a name (`user_id`):

```python
work = GoogleAuth(user_id="work")
work.authenticate()              # logs in and stores the token as "work"

home = GoogleAuth(user_id="home")
work.accounts()                  # ["home", "work"]
work.stored_scopes()             # scopes granted to "work"
```

Without `user_id`, the account is `GSUITE_ACCOUNT` (default: `default`). A
login replaces the account's stored scopes; to add access, log in with
`stored_scopes()` plus the new ones (`gsuite auth login --add --scopes tasks`
does exactly that). A custom `TokenStore` implements `list_users()` to support
`accounts()`.

## Configuration

Environment variables (prefix `GSUITE_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `GSUITE_CREDENTIALS_FILE` | credentials.json | OAuth credentials |
| `GSUITE_TOKEN_STORAGE` | sqlite | sqlite, secretmanager or keyring |
| `GSUITE_ACCOUNT` | default | Which stored login to use when `user_id` isn't given |
| `GSUITE_KEYRING_SERVICE` | gsuite-sdk | Keyring service the tokens are filed under |
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
