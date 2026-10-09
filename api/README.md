# gsuite-api

Unified FastAPI REST gateway for Google Workspace APIs.

## Installation

The API ships inside `gsuite-sdk` as the `api` extra (add `cli` for the
`gsuite serve` command):

```bash
pip install "gsuite-sdk[api,cli]"
```

## Quick Start

```bash
# Start the server
gsuite serve --port 8080

# Or with uvicorn directly
uvicorn gsuite_api.main:app --port 8080
```

Server runs at `http://localhost:8080` with interactive docs at `/docs`.

## Docker

```bash
# Build (from the repo root)
docker build -f api/Dockerfile -t gsuite-api .

# Run (mount credentials)
docker run -p 8080:8080 \
  -v ~/.gsuite/credentials.json:/app/credentials.json \
  -v ~/.gsuite/tokens.db:/app/tokens.db \
  gsuite-api
```

## Endpoints

### Health

```bash
GET /health
```

### Gmail

```bash
# Messages (query uses Gmail search syntax)
GET /gmail/messages?query=from:boss@company.com+newer_than:7d&limit=10
GET /gmail/messages/unread            # also: starred, important, sent
GET /gmail/messages/{message_id}

# Send, reply (same thread; reply_all optional), forward
POST /gmail/messages/send                    {"to": ["user@example.com"], "subject": "Hello", "body": "World"}
POST /gmail/messages/{message_id}/reply      {"body": "Thanks", "reply_all": true}
POST /gmail/messages/{message_id}/forward    {"to": ["colleague@example.com"], "body": "FYI"}

# Actions on one message
POST /gmail/messages/{message_id}/read       # also: unread, star, important, archive, inbox, untrash
DELETE /gmail/messages/{message_id}          # trash
POST /gmail/messages/{message_id}/labels     {"add_labels": ["Work"], "remove_labels": ["INBOX"]}
GET /gmail/messages/{message_id}/attachments/{attachment_id}

# Many messages at once (one batchModify per 1000 IDs)
POST /gmail/messages/batch/read      {"message_ids": ["a", "b"]}
POST /gmail/messages/batch/labels    {"message_ids": ["a", "b"], "add_labels": ["Work"]}

# Threads
GET /gmail/threads?query=from:ana&limit=25
GET /gmail/threads/{thread_id}

# Drafts
GET /gmail/drafts
POST /gmail/drafts                   {"to": ["a@example.com"], "subject": "Proposal", "body": "..."}
GET /gmail/drafts/{draft_id}
POST /gmail/drafts/{draft_id}/send
DELETE /gmail/drafts/{draft_id}

# Labels (by name or ID) and filters
GET /gmail/labels
POST /gmail/labels                   {"name": "Clients/Acme"}
PATCH /gmail/labels/{label}          {"name": "Customers"}
DELETE /gmail/labels/{label}
GET /gmail/filters
POST /gmail/filters                  {"criteria": {"from": "alerts@x.com"}, "action": {"addLabelIds": ["Alerts"]}}
DELETE /gmail/filters/{filter_id}

GET /gmail/profile
```

### Calendar

All routes take an optional `calendar_id` query parameter (default: primary).

```bash
GET /calendar/events?days=7&limit=100        # upcoming
GET /calendar/events/today                   # in GSUITE_DEFAULT_TIMEZONE
GET /calendar/events/{event_id}
GET /calendar/events/{event_id}/instances    # occurrences of a recurring event

# Create; meet=true adds a Google Meet link, send_updates emails invitees
POST /calendar/events
{
  "summary": "Meeting",
  "start": "2026-02-15T10:00:00-03:00",
  "end": "2026-02-15T11:00:00-03:00",
  "attendees": ["user@example.com"],
  "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
  "meet": true,
  "send_updates": "all"
}
POST /calendar/events:quickAdd       {"text": "Lunch with Ana tomorrow at 1pm"}

# Update (only the fields sent change) and delete
PATCH /calendar/events/{event_id}    {"summary": "Renamed", "send_updates": "all"}
DELETE /calendar/events/{event_id}?send_updates=all

# Free/busy ("me" = your primary calendar)
POST /calendar/freebusy   {"time_min": "...", "time_max": "...", "calendars": ["me", "ana@example.com"]}

GET /calendar/calendars
```

### Drive

```bash
# List files (trashed=true for the trash)
GET /drive/files?parent_id=folder_id&mime_type=application/pdf&limit=100

# Metadata
GET /drive/files/{file_id}

# Download; Google Docs/Sheets/Slides are exported (export=pdf|docx|xlsx|csv|...)
GET /drive/files/{file_id}/content
GET /drive/files/{file_id}/content?export=pdf

# Upload (multipart/form-data: file, parent_id?, name?)
POST /drive/files/upload

# Rename / describe / star (only the fields sent change)
PATCH /drive/files/{file_id}
{"name": "New name.pdf"}

# Copy and move
POST /drive/files/{file_id}/copy   {"name": "Copy", "parent_id": "folder_id"}
POST /drive/files/{file_id}/move   {"parent_id": "folder_id"}

# Trash, restore, delete (DELETE trashes unless permanent=true)
POST /drive/files/{file_id}/trash
POST /drive/files/{file_id}/restore
DELETE /drive/files/{file_id}?permanent=true

# Folders
POST /drive/folders   {"name": "New Folder", "parent_id": "optional_parent_id"}

# Sharing
GET /drive/files/{file_id}/permissions
POST /drive/files/{file_id}/permissions   {"type": "user", "email": "a@example.com", "role": "writer"}
POST /drive/files/{file_id}/permissions   {"type": "anyone", "role": "reader"}
DELETE /drive/files/{file_id}/permissions/{permission_id}
```

Uploads pass through the API server; behind Cloud Run the request limit is 32 MB.

### Sheets

Ranges in paths are full A1 references including the sheet, e.g.
`Sheet1!A1:C10` or `'Q1 Budget'!A:A`.

```bash
# Spreadsheets
GET /sheets/list?limit=50
GET /sheets/{spreadsheet_id}                 # metadata + worksheets
POST /sheets/create?title=Budget

# Values
GET /sheets/{spreadsheet_id}/values/Sheet1!A1:C10
GET /sheets/{spreadsheet_id}/values:batchGet?ranges=Sheet1!A1:B2&ranges=Sheet2!C:C
PUT /sheets/{spreadsheet_id}/values/Sheet1!A1:C2?value_input=RAW
{"range": "Sheet1!A1:C2", "values": [["Name", "Age"], ["Alice", 30]]}
POST /sheets/{spreadsheet_id}/values/Sheet1:append    {"values": [["Bob", 25]]}
POST /sheets/{spreadsheet_id}/values:batchUpdate      {"data": [{"range": "A1", "values": [[1]]}]}
DELETE /sheets/{spreadsheet_id}/values/Sheet1!A1:C10

# Find and replace (all sheets unless sheet_id)
POST /sheets/{spreadsheet_id}:findReplace   {"find": "2025", "replacement": "2026"}

# Worksheets (sheet_id is the numeric gid)
POST /sheets/{spreadsheet_id}/worksheets                     {"title": "Q2"}
PATCH /sheets/{spreadsheet_id}/worksheets/{sheet_id}         {"title": "Q2 2026"}
DELETE /sheets/{spreadsheet_id}/worksheets/{sheet_id}
POST /sheets/{spreadsheet_id}/worksheets/{sheet_id}/duplicate {"title": "Backup"}
POST /sheets/{spreadsheet_id}/worksheets/{sheet_id}/format   {"range": "A1:Z1", "format": {"textFormat": {"bold": true}}}
POST /sheets/{spreadsheet_id}/worksheets/{sheet_id}/freeze   {"rows": 1}
POST /sheets/{spreadsheet_id}/worksheets/{sheet_id}/protect  {"range": "A1:A100", "editors": ["admin@example.com"]}
```

`value_input` is `USER_ENTERED` by default (formulas and dates are parsed as
in the UI); send `RAW` when writing untrusted text.

## Authentication

### Local Development

The API uses OAuth tokens from the local token store:

```bash
# First, authenticate via CLI
gsuite auth login

# Then start the server
gsuite serve
```

### Cloud Run / Production

For production, use Secret Manager for token storage:

```bash
# Set environment variables
export GSUITE_TOKEN_STORAGE=secretmanager
export GSUITE_GCP_PROJECT_ID=my-project

# Token is read from Secret Manager
gsuite serve
```

### API Key

Every endpoint except `GET /health` requires the `X-API-Key` header:

```bash
export GSUITE_API_KEY=your-secret-api-key
gsuite serve
curl -H "X-API-Key: your-secret-api-key" http://localhost:8080/gmail/messages
```

The API **fails closed**: if `GSUITE_API_KEY` is not set, every request gets
a 401. If access is already restricted some other way (Cloud Run with
`--no-allow-unauthenticated` and IAM, or a server bound to localhost), opt out
explicitly with `GSUITE_ALLOW_NO_API_KEY=true`.

`GET /health/admin/logs` uses a separate key in the `X-Admin-Key` header
(`ADMIN_API_KEY` env var). Keys are not accepted in query strings.

### CORS

CORS is disabled unless you list origins:

```bash
export GSUITE_CORS_ORIGINS="https://app.example.com,https://admin.example.com"
```

Cookies/credentials are never allowed; browsers send the API key as a header.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GSUITE_HOST` | 127.0.0.1 | Server host (`0.0.0.0` exposes it to your network) |
| `GSUITE_PORT` | 8080 | Server port |
| `GSUITE_API_KEY` | - | API key required in `X-API-Key` |
| `GSUITE_ALLOW_NO_API_KEY` | false | Serve without an API key (see above) |
| `GSUITE_CORS_ORIGINS` | - | Comma-separated allowed origins |
| `GSUITE_LOG_LEVEL` | INFO | Log level |
| `GSUITE_LOG_FORMAT` | text | `json` for one JSON object per line (Cloud Logging) |
| `GSUITE_CREDENTIALS_FILE` | credentials.json | OAuth credentials |
| `GSUITE_TOKEN_STORAGE` | sqlite | Token storage backend |
| `GSUITE_TOKEN_DB_PATH` | tokens.db | SQLite token path |
| `GSUITE_GCP_PROJECT_ID` | - | GCP project for Secret Manager |

## Error Responses

Errors use [RFC 9457 problem details](https://www.rfc-editor.org/rfc/rfc9457)
with `Content-Type: application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Rate limit exceeded for gmail",
  "instance": "/gmail/messages",
  "request_id": "3f2a9c...",
  "service": "gmail"
}
```

| Code | When |
|------|------|
| 401 | Missing/invalid API key, or the server has no valid Google token |
| 403 | Google denied the operation |
| 404 | Resource or route not found |
| 422 | Invalid request (`errors` lists each field) |
| 429 | Google rate limit or quota (`Retry-After` when Google sends one) |
| 502 | Google returned an error the API doesn't map |
| 500 | Unexpected error; the response never includes internals |

Every response carries an `X-Request-ID` header (yours, if you send a valid
one), and `request_id` appears in error bodies and logs so a failed call can
be traced.

## OpenAPI Schema

Full OpenAPI spec available at:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- JSON: `http://localhost:8080/openapi.json`

## License

MIT
