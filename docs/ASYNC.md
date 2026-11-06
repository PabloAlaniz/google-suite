# Async

```bash
pip install "gsuite-sdk[async]"     # httpx; included in [all]
```

## Foundation: `gsuite_core.aio.AsyncGoogleClient`

googleapiclient is synchronous, so async clients call Google's REST APIs
directly through `AsyncGoogleClient` (httpx). It applies exactly the policies
of the sync path, from the same code in `gsuite_core.api_utils`:

- **Auth**: the same `GoogleAuth` (OAuth or service account). Expired tokens
  are refreshed in a worker thread, once even when many requests wait for it;
  `GoogleAuth.refresh()` persists the new token.
- **Retries**: rate limits (429, or 403 `rateLimitExceeded`) for any method;
  5xx and network failures only for idempotent methods (a `POST` that timed
  out may already have been applied). Full-jitter backoff, `Retry-After`
  honored. `GSUITE_MAX_RETRIES`, `GSUITE_RETRY_DELAY`, `GSUITE_REQUEST_TIMEOUT`.
- **Errors**: the same `GSuiteError` types (`NotFoundError`,
  `RateLimitError`, `PermissionDeniedError`, `APIError`, ...).
- **Pagination**: `async for item in http.paginate(url, "items", service=...)`.

```python
from gsuite_core.aio import AsyncGoogleClient

async with AsyncGoogleClient(auth) as http:
    profile = await http.json(
        "GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", service="gmail"
    )
```

## Rate limiting (sync and async)

`GSUITE_RATE_LIMIT=5` caps the process at 5 Google requests per second
(token bucket, burst `GSUITE_RATE_LIMIT_BURST`, default `max(1, rate)`).
Both `execute()` (sync clients) and `AsyncGoogleClient` draw from the same
bucket. Off by default.

## Sheets

`AsyncSheets` / `AsyncSpreadsheet` / `AsyncWorksheet` cover values,
streaming, tables and typed rows. Formatting, validation, charts and
structure changes stay sync-only (`Sheets`).

```python
from gsuite_sheets import AsyncSheets

async with AsyncSheets(auth) as sheets:
    doc = await sheets.open("Budget")
    ws = doc.worksheet("Data")                       # no request: tabs load with the doc
    await ws.upsert([{"id": "7", "status": "paid"}], key="id")
    async for invoice in ws.iter_as(Invoice):
        ...
    pdf = await doc.export("pdf")
```

For tests, `gsuite_sheets.engine.testing.rest_fake.fake_async_sheets(backend.client)`
returns a real `AsyncSheets` over the in-memory emulator.

## Gmail

`AsyncGmail` mirrors `Gmail` for messages, threads, labels (`batch_modify`
included), drafts, send, reply and forward. Filters stay sync-only. Where the
sync client sends an HTTP batch, the async one runs the requests concurrently
(`concurrency=10` by default). Message parsing and MIME building are the sync
client's own code.

```python
from gsuite_gmail import AsyncGmail

async with AsyncGmail(auth) as gmail:
    unread = await gmail.get_unread()
    await gmail.batch_modify([m.id for m in unread], remove_labels=["UNREAD"])
    await gmail.reply(unread[0], "Thanks!")
```

Messages from `AsyncGmail` have no sync client behind them, so their fluent
methods (`message.trash()`, `attachment.download()` for attachments not sent
inline) raise `TypeError` instead of silently doing nothing; await
`gmail.trash(id)`, `gmail.batch_modify(...)` or
`gmail.download_attachment(message_id, attachment_id)` instead.

## Calendar

`AsyncCalendar` mirrors `Calendar`: events (list, get, create with Meet and
recurrence, quick add, update, instances, delete), calendars and free/busy,
with the same arguments and results. Request bodies come from the same code as
the sync client, so naive datetimes mean the same thing in both
(`GSUITE_DEFAULT_TIMEZONE` for event times, UTC for query bounds).

```python
from gsuite_calendar import AsyncCalendar

async with AsyncCalendar(auth) as cal:
    events = await cal.get_upcoming(days=7)
    busy = await cal.get_free_busy(start, end, ["me", "ana@example.com"])
    await cal.create_event("Standup", datetime(2026, 3, 2, 9), meet=True)
```

## Drive

`AsyncDrive` mirrors `Drive`: listing and search, metadata (get, update,
rename, copy, move), download and export, uploads, folders, trash and delete,
and permissions.

```python
from gsuite_drive import AsyncDrive

async with AsyncDrive(auth) as drive:
    files = await drive.search("budget")
    await drive.download(files[0].id, "budget.xlsx", export_format="xlsx")
    await drive.upload("report.pdf", parent_id=folder_id, on_progress=print)
```

Uploads are resumable and go in chunks (`chunk_size`, 8 MiB by default, a
multiple of 256 KiB). When a chunk fails with a network error, a 5xx or a
429, the client asks Drive how many bytes it kept and resumes from there
(up to `GSUITE_MAX_RETRIES` times in a row), so a retry never resends bytes
Drive already has. Errors a retry can't fix (403, 404, ...) raise at once.
Downloads and exports are read into memory, as in the sync client.

Files from `AsyncDrive` have no sync client behind them: `file.trash()`,
`file.download()` and `folder.list_files()` raise `TypeError`; await the
`AsyncDrive` method instead.

## REST API

Routers backed by an async client run as `async def` routes on the event
loop instead of FastAPI's thread pool: **Calendar** (`/calendar`) and **Drive**
(`/drive`; uploads stream the request's file to Drive in chunks). Each request
gets its own client, closed when the response is sent, as the sync routes
build theirs per request. The other routers stay sync until their services
have async clients.

## Shared code

Each async client is a thin I/O layer: parsers, query strings, request
bodies and MIME building are the sync client's own code (`gsuite_gmail._mime`,
`gsuite_calendar._requests`, `gsuite_drive._requests`), the way the Sheets
adapters share their request builders. A behavior fixed in one client is
fixed in both.
