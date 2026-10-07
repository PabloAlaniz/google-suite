"""A fake Sheets v4 / Drive v3 REST server (httpx transport) over the in-memory emulator.

``fake_rest_transport(client)`` answers the REST calls the async adapter sends
by delegating to ``FakeGoogleService`` (the googleapiclient-shaped fake), so
both adapters are exercised against the same emulator.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

from gsuite_sheets.engine.domain.errors import SpreadsheetNotFoundError, WorksheetNotFoundError

from .google_api_fake import FakeGoogleService
from .in_memory import InMemoryClient

SHEETS = "/v4/spreadsheets"
DRIVE = "/drive/v3/files"


def _flag(value: str | None, default: bool = False) -> bool:
    return default if value is None else value.lower() == "true"


def _route(fake: FakeGoogleService, method: str, path: str, params: Any, body: Any) -> Any:
    """Dispatch one REST call; returns JSON-able data or bytes."""
    segments = [unquote(s) for s in path.split("/")]

    if path.startswith(DRIVE):
        rest = segments[4:]  # after /drive/v3/files
        files = fake.files()
        if not rest:
            return files.list(
                q=params.get("q", ""), pageSize=int(params.get("pageSize", 0))
            ).execute()
        file_id = rest[0]
        if len(rest) == 1:
            if method == "PATCH":
                return files.update(file_id).execute()
            if method == "DELETE":
                return files.delete(file_id).execute()
        if rest[1:] == ["copy"]:
            return files.copy(file_id, body=body or {}).execute()
        if rest[1:] == ["export"]:
            return files.export(file_id, params["mimeType"]).execute()
        if rest[1] == "permissions":
            permissions = fake.permissions()
            if len(rest) == 3:
                return permissions.delete(file_id, rest[2]).execute()
            if method == "POST":
                extra: dict[str, Any] = {
                    "sendNotificationEmail": _flag(params.get("sendNotificationEmail"))
                }
                if "emailMessage" in params:
                    extra["emailMessage"] = params["emailMessage"]
                return permissions.create(file_id, body=body, **extra).execute()
            return permissions.list(file_id).execute()

    if path.startswith(SHEETS):
        sheets = fake.spreadsheets()
        rest = segments[3:]  # after /v4/spreadsheets
        if not rest:
            return sheets.create(body=body).execute()
        head = rest[0]
        if head.endswith(":batchUpdate") and len(rest) == 1:
            return sheets.batchUpdate(head[: -len(":batchUpdate")], body=body).execute()
        if len(rest) == 1:
            return sheets.get(
                head, fields=params.get("fields", ""), ranges=params.get_list("ranges") or None
            ).execute()
        spreadsheet_id = head
        values = sheets.values()
        if rest[1] == "values:batchUpdate":
            return values.batchUpdate(spreadsheet_id, body=body).execute()
        if rest[1] == "values:batchClear":
            return values.batchClear(spreadsheet_id, body=body).execute()
        if rest[1] == "values":
            a1_range = "/".join(rest[2:])
            if a1_range.endswith(":append"):
                return values.append(
                    spreadsheet_id,
                    a1_range[: -len(":append")],
                    body=body,
                    valueInputOption=params.get("valueInputOption", "USER_ENTERED"),
                ).execute()
            if a1_range.endswith(":clear"):
                return values.clear(spreadsheet_id, a1_range[: -len(":clear")]).execute()
            if method == "PUT":
                return values.update(
                    spreadsheet_id, a1_range, params["valueInputOption"], body=body
                ).execute()
            return values.get(
                spreadsheet_id, a1_range, valueRenderOption=params.get("valueRenderOption")
            ).execute()
        if rest[1] == "sheets" and rest[2].endswith(":copyTo"):
            sheet_id = int(rest[2][: -len(":copyTo")])
            return sheets.sheets().copyTo(spreadsheet_id, sheet_id, body=body).execute()

    raise NotImplementedError(f"{method} {path}")


def fake_rest_transport(client: InMemoryClient) -> Any:
    """An ``httpx.MockTransport`` serving Sheets/Drive REST calls from ``client``."""
    import httpx

    fake = FakeGoogleService(client)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        try:
            result = _route(
                fake,
                request.method,
                request.url.raw_path.decode().split("?")[0],
                request.url.params,
                body,
            )
        except (SpreadsheetNotFoundError, WorksheetNotFoundError, KeyError) as exc:
            return httpx.Response(404, json={"error": {"code": 404, "message": str(exc)}})
        if isinstance(result, bytes):
            return httpx.Response(200, content=result)
        return httpx.Response(200, json=result if result is not None else {})

    return httpx.MockTransport(handler)


class FakeCredentials:
    """Always-valid credentials for tests."""

    valid = True

    def apply(self, headers: dict[str, str]) -> None:
        headers["authorization"] = "Bearer fake"


def async_adapter_client(client: InMemoryClient) -> Any:
    """An ``AsyncGoogleApiClient`` (the real async adapter) whose requests hit ``client``."""
    from gsuite_core.aio import AsyncGoogleClient
    from gsuite_sheets.engine_async_adapter import AsyncGoogleApiClient

    return AsyncGoogleApiClient(
        AsyncGoogleClient(FakeCredentials(), transport=fake_rest_transport(client))
    )


def fake_async_sheets(client: InMemoryClient, **options: Any) -> Any:
    """A real ``gsuite_sheets.AsyncSheets`` over the emulator, for async tests::

    backend = InMemoryBackend()
    backend.add_spreadsheet("Budget", {"Data": [["name"]]})
    async with fake_async_sheets(backend.client) as sheets:
        ws = (await sheets.open("Budget")).worksheet("Data")
    """
    from gsuite_sheets.aio import AsyncSheets

    return AsyncSheets(FakeCredentials(), transport=fake_rest_transport(client), **options)
