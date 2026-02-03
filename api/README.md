# gsuite-api

Unified FastAPI REST gateway for Google Workspace APIs.

## Installation

```bash
pip install gsuite-api
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
# Build
docker build -t gsuite-api .

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
# List messages
GET /gmail/messages
GET /gmail/messages?query=is:unread&max_results=10

# Get unread
GET /gmail/messages/unread

# Get single message
GET /gmail/messages/{message_id}

# Send email
POST /gmail/messages/send
{
  "to": ["user@example.com"],
  "subject": "Hello",
  "body": "World"
}

# List labels
GET /gmail/labels

# Search
GET /gmail/search?q=from:boss@company.com+newer_than:7d
```

### Calendar

```bash
# Get events
GET /calendar/events
GET /calendar/events?time_min=2026-02-01&time_max=2026-02-28

# Get today's events
GET /calendar/events/today

# Get upcoming events
GET /calendar/events/upcoming?days=7

# Create event
POST /calendar/events
{
  "summary": "Meeting",
  "start": "2026-02-15T10:00:00",
  "end": "2026-02-15T11:00:00",
  "attendees": ["user@example.com"]
}

# Delete event
DELETE /calendar/events/{event_id}

# List calendars
GET /calendar/calendars
```

### Drive

```bash
# List files
GET /drive/files
GET /drive/files?parent_id=folder_id&mime_type=application/pdf

# Get file info
GET /drive/files/{file_id}

# Download file
GET /drive/files/{file_id}/download

# Upload file
POST /drive/files/upload
Content-Type: multipart/form-data
file: <binary>
parent_id: <optional>

# Create folder
POST /drive/folders
{
  "name": "New Folder",
  "parent_id": "optional_parent_id"
}

# Delete file
DELETE /drive/files/{file_id}
```

### Sheets

```bash
# Get spreadsheet info
GET /sheets/{spreadsheet_id}

# Get worksheet data
GET /sheets/{spreadsheet_id}/{sheet_name}
GET /sheets/{spreadsheet_id}/{sheet_name}?range=A1:C10

# Update data
PUT /sheets/{spreadsheet_id}/{sheet_name}
{
  "range": "A1:C2",
  "values": [
    ["Name", "Age", "City"],
    ["Alice", 30, "NYC"]
  ]
}

# Append rows
POST /sheets/{spreadsheet_id}/{sheet_name}/append
{
  "values": [
    ["Bob", 25, "LA"]
  ]
}
```

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

### API Key Protection

Protect endpoints with an API key:

```bash
export GSUITE_API_KEY=your-secret-api-key
gsuite serve
```

Then include the key in requests:

```bash
curl -H "X-API-Key: your-secret-api-key" http://localhost:8080/gmail/messages
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GSUITE_HOST` | 0.0.0.0 | Server host |
| `GSUITE_PORT` | 8080 | Server port |
| `GSUITE_API_KEY` | - | API key for auth (optional) |
| `GSUITE_CREDENTIALS_FILE` | credentials.json | OAuth credentials |
| `GSUITE_TOKEN_STORAGE` | sqlite | Token storage backend |
| `GSUITE_TOKEN_DB_PATH` | tokens.db | SQLite token path |
| `GSUITE_GCP_PROJECT_ID` | - | GCP project for Secret Manager |

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": 404,
    "message": "Message not found",
    "details": {}
  }
}
```

Common status codes:

| Code | Description |
|------|-------------|
| 400 | Bad request (invalid parameters) |
| 401 | Not authenticated |
| 403 | Permission denied |
| 404 | Resource not found |
| 429 | Rate limited |
| 500 | Internal error |

## OpenAPI Schema

Full OpenAPI spec available at:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
- JSON: `http://localhost:8080/openapi.json`

## License

MIT
