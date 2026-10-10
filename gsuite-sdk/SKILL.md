---
name: gsuite-sdk
description: Work with Gmail, Google Calendar, Drive, Sheets, Tasks and Contacts through the gsuite-sdk Python library and its `gsuite` CLI (JSON output for agents). Use it to read and send email, manage events, upload and share files, read and write spreadsheets, and manage tasks and contacts.
metadata:
  openclaw:
    requires:
      env:
        - GSUITE_CREDENTIALS_FILE
    primaryEnv: GSUITE_CREDENTIALS_FILE
    install:
      - kind: pip
        package: "gsuite-sdk[cli]"
        bins: [gsuite]
    homepage: https://pabloalaniz.github.io/google-suite/
---

# gsuite-sdk

One OAuth login for Gmail, Calendar, Drive, Sheets, Tasks and Contacts, usable
three ways: the `gsuite` CLI (prefer it: most commands print JSON with
`-o json`), the Python SDK, or a REST API (`gsuite serve`).

Docs: https://pabloalaniz.github.io/google-suite/ · Source: https://github.com/PabloAlaniz/google-suite

## Setup

```bash
pip install "gsuite-sdk[cli]"      # the gsuite command; [all] adds the REST API, async and Secret Manager
```

Configuration comes from environment variables (or a `.env` file):

| Variable | Default | Meaning |
|---|---|---|
| `GSUITE_CREDENTIALS_FILE` | `credentials.json` | OAuth client file from Google Cloud ([how to get it](https://pabloalaniz.github.io/google-suite/GETTING_CREDENTIALS/)) |
| `GSUITE_TOKEN_DB_PATH` | `tokens.db` | Where the login token is stored (SQLite) |
| `GSUITE_DEFAULT_TIMEZONE` | `UTC` | Time zone for "today" and for naive datetimes |

Both paths are **relative to the current directory**: run every command from
the same place, or set absolute paths. Set `GSUITE_DEFAULT_TIMEZONE` (e.g.
`America/Argentina/Buenos_Aires`), or "today" and new events use UTC.

### Login (once, opens a browser)

```bash
gsuite auth login                                  # Gmail, Calendar, Drive, Sheets
gsuite auth login --force --scopes default,tasks,contacts   # add Tasks and Contacts
gsuite auth status
```

`--scopes` takes a comma-separated list of `default, gmail, calendar, drive,
sheets, tasks, contacts, all`. Tasks and Contacts are not in the default login.
The token refreshes itself; log in again (`--force`) only after a
`TokenRefreshError` or when a call fails with `PermissionDeniedError` because a
scope is missing.

Without a browser (servers, CI) use a service account:

```python
from gsuite_core import GoogleAuth, Scopes

auth = GoogleAuth.from_service_account(
    "service-account.json",
    scopes=Scopes.default(),
    subject="user@your-domain.com",  # Workspace domain-wide delegation; omit otherwise
)
```

## CLI (preferred)

Add `-o json` where supported and parse stdout. Errors exit with code 1 and a
one-line message.

```bash
gsuite gmail list --unread --limit 10 -o json
gsuite gmail list --query "from:boss@example.com newer_than:7d" -o json
gsuite gmail read MESSAGE_ID -o json
gsuite gmail send --to ana@example.com --subject "Report" --body "Attached." --attach report.pdf
gsuite gmail reply MESSAGE_ID --body "Thanks!"

gsuite calendar list --days 1 -o json        # events in the next 24 hours
gsuite calendar create "Sync" --start "2026-03-02 10:00" --end "2026-03-02 10:30" --attendee ana@example.com --meet --notify

gsuite drive list --name "invoice" -o json
gsuite drive upload ./report.pdf --to FOLDER_ID
gsuite drive download FILE_ID --out ./file.pdf
gsuite drive share FILE_ID ana@example.com --role writer

gsuite sheets read SPREADSHEET --range "A1:D20" -o json   # SPREADSHEET: title, ID or URL
gsuite sheets append SPREADSHEET --value "Ana" --value 42
gsuite sheets export SPREADSHEET --format xlsx --out ./budget.xlsx

gsuite tasks list -o json
gsuite tasks add "Pay rent" --due 2026-03-01
gsuite tasks done TASK_ID

gsuite contacts search ana -o json
```

No JSON output on `calendar today`, `calendar week` or `gmail search`: use
`calendar list --days N -o json` and `gmail list --query ... -o json` instead.

## Python SDK

```python
from gsuite_core import GoogleAuth
from gsuite_gmail import Gmail, query
from gsuite_calendar import Calendar
from gsuite_drive import Drive
from gsuite_sheets import Sheets

auth = GoogleAuth()   # reads the token saved by `gsuite auth login`

gmail = Gmail(auth)
for msg in gmail.search(query.from_("boss@example.com") & query.newer_than(days=7)):
    print(msg.subject, msg.sender, msg.date)

calendar = Calendar(auth)
for event in calendar.get_today():
    print(event.start, event.summary, event.meet_link)

drive = Drive(auth)
uploaded = drive.upload("report.pdf", parent_id="FOLDER_ID")
drive.share(uploaded.id, "ana@example.com", role="reader")

sheets = Sheets(auth)
spreadsheet = sheets.open_by_key("1AbC...")     # by ID; sheets.open(title) searches by title
ws = spreadsheet.sheet1                         # first tab, whatever its name
rows = ws.get_all_records()                     # list of dicts; values are strings
ws.append_rows([["Ana", 42], ["Bob", 7]])
ws.update("A1", [["Name", "Score"]])            # values are always a 2D list
```

Per service, with everything else the SDK can do:
[Gmail](references/gmail.md) · [Calendar](references/calendar.md) ·
[Drive](references/drive.md) · [Sheets](references/sheets.md) ·
[Tasks and Contacts](references/tasks-contacts.md) ·
[REST API and deployment](references/rest-api.md)

## Errors and return values

- Lookups return `None` when the item doesn't exist (`gmail.get_message`,
  `calendar.get_event`, `drive.get`, `tasks.get_task`, `contacts.get`), and
  deletes return `False`. Check for them instead of catching exceptions.
- Every error is a `gsuite_core.GSuiteError`:
  - `NotFoundError`: HTTP 404 from Google.
  - `PermissionDeniedError`: HTTP 403, usually a scope missing from the login
    (log in again with `--force --scopes ...`) or no access to that item.
  - `RateLimitError` / `QuotaExceededError`: already retried with backoff
    before being raised.
  - `ValidationError`: bad input (`.field` names it).
  - `CredentialsNotFoundError`: `GSUITE_CREDENTIALS_FILE` doesn't exist and a
    browser login is needed.
  - `NotAuthenticatedError` / `TokenRefreshError`: run `gsuite auth login`.
- Sheets: `sheets.open(title)` raises `ValueError` when no spreadsheet has
  that title (use `open_by_key` when you have the ID); engine operations raise
  `SpreadsheetNotFoundError`, `WorksheetNotFoundError` and `InvalidRangeError`
  (all `GSuiteError`).

## Notes for agents

- Confirm with the user before sending email, inviting attendees
  (`--notify` / `send_updates="all"`), sharing files or deleting anything.
- Gmail search uses Gmail's query syntax (`from:`, `newer_than:7d`,
  `has:attachment`, `is:unread`), or the `query` builder in Python.
- Dates for `--due`, `--start` and the SDK are ISO (`2026-03-01`,
  `2026-03-01 10:00`); naive times are in `GSUITE_DEFAULT_TIMEZONE`.
