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

## Roadmap: Gmail, Calendar, Drive

They build on `AsyncGoogleClient`; nothing else in the foundation is
service-specific.

| Service | Scope | Notes |
|---|---|---|
| Gmail | list/get (concurrent gets with a semaphore instead of HTTP batch), send/reply/forward (raw MIME from the sync composer), labels, drafts, batchModify | reuse `GmailParser` and the sync `_compose` |
| Calendar | events list/get/create/update/delete, free/busy, instances | reuse `CalendarParser`, `_rfc3339`, `_time_bodies` |
| Drive | list/get/metadata ops, export, permissions; downloads and resumable uploads streamed with httpx | uploads are the only new protocol work |

The pure parts (parsers, MIME composition, request bodies) are shared with
the sync clients, the way the Sheets adapters share their request builders,
so each async client is a thin I/O layer.
