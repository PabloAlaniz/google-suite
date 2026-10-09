"""A googleapiclient-shaped Sheets + Drive service backed by the in-memory backend.

``FakeGoogleService(client)`` answers the calls google-suite makes
(``service.spreadsheets().values().get(...).execute()``, ``files().list(...)``,
``permissions().create(...)``, ...) by operating on an ``InMemoryClient``. It
lets the real adapter (``gsuite_sheets.engine_adapter``) run end to end without
network, and is what the engine's parity run uses (``--engine-backend=adapter``).

Only the request shapes the adapter sends are supported.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from gsuite_sheets.a1 import a1, split_sheet

from .in_memory import InMemoryClient, InMemorySpreadsheet, InMemoryWorksheet


class FakeRequest:
    """A request whose execute() runs the in-memory operation."""

    def __init__(self, method: str, fn: Callable[[], Any]) -> None:
        self.method = method
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


def _split(a1_range: str) -> tuple[str | None, str | None]:
    """'Title'!A1:B2 -> ("Title", "A1:B2"); 'Title' -> ("Title", None); A1 -> (None, "A1")."""
    return split_sheet(a1_range)


def _unescape(literal: str) -> str:
    return literal.replace("\\'", "'").replace("\\\\", "\\")


class _Values:
    def __init__(self, service: FakeGoogleService) -> None:
        self._s = service

    def _target(self, spreadsheet_id: str, a1_range: str) -> tuple[InMemoryWorksheet, str | None]:
        ss = self._s.spreadsheet(spreadsheet_id)
        title, cells = _split(a1_range)
        if title is None:
            ws = ss.worksheets[0]
        else:
            ws = ss.worksheet(title)  # type: ignore[assignment]
        return ws, cells

    def get(
        self, spreadsheetId: str, range: str, valueRenderOption: str | None = None
    ) -> FakeRequest:
        def run() -> Any:
            ws, cells = self._target(spreadsheetId, range)
            if cells is None:
                rows = _trim(ws.get_all_values(valueRenderOption))
                return {"values": rows} if rows else {}
            return self._s.spreadsheet(spreadsheetId).values_get(a1(ws.title, cells))

        return FakeRequest("GET", run)

    def batchGet(
        self, spreadsheetId: str, ranges: list[str], valueRenderOption: str | None = None
    ) -> FakeRequest:
        return FakeRequest(
            "GET",
            lambda: {
                "valueRanges": [
                    self.get(spreadsheetId, r, valueRenderOption).execute() for r in ranges
                ]
            },
        )

    def update(
        self, spreadsheetId: str, range: str, valueInputOption: str, body: dict[str, Any]
    ) -> FakeRequest:
        def run() -> Any:
            ws, cells = self._target(spreadsheetId, range)
            ws.update(body["values"], valueInputOption, cells)
            return {"updatedCells": sum(len(r) for r in body["values"])}

        return FakeRequest("PUT", run)

    def append(
        self, spreadsheetId: str, range: str, body: dict[str, Any], **params: Any
    ) -> FakeRequest:
        def run() -> Any:
            ws, _ = self._target(spreadsheetId, range)
            ws.append_rows(body["values"], params.get("valueInputOption", "USER_ENTERED"))
            return {"updates": {"updatedRows": len(body["values"])}}

        return FakeRequest("POST", run)

    def clear(self, spreadsheetId: str, range: str) -> FakeRequest:
        def run() -> Any:
            ws, cells = self._target(spreadsheetId, range)
            if cells is None:
                ws.clear()
            else:
                ws.batch_clear([cells])
            return {}

        return FakeRequest("POST", run)

    def batchClear(self, spreadsheetId: str, body: dict[str, Any]) -> FakeRequest:
        return FakeRequest(
            "POST", lambda: [self.clear(spreadsheetId, r).execute() for r in body["ranges"]] and {}
        )

    def batchUpdate(self, spreadsheetId: str, body: dict[str, Any]) -> FakeRequest:
        def run() -> Any:
            for item in body["data"]:
                ws, cells = self._target(spreadsheetId, item["range"])
                ws.batch_update(
                    [{"range": cells, "values": item["values"]}], body["valueInputOption"]
                )
            return {"responses": []}

        return FakeRequest("POST", run)


class _Sheets:
    def __init__(self, service: FakeGoogleService) -> None:
        self._s = service

    def copyTo(self, spreadsheetId: str, sheetId: int, body: dict[str, Any]) -> FakeRequest:
        def run() -> Any:
            ss = self._s.spreadsheet(spreadsheetId)
            ws = next(w for w in ss.worksheets if w.id == sheetId)
            return ws.copy_to(body["destinationSpreadsheetId"])

        return FakeRequest("POST", run)


class _Spreadsheets:
    def __init__(self, service: FakeGoogleService) -> None:
        self._s = service

    def values(self) -> _Values:
        return _Values(self._s)

    def sheets(self) -> _Sheets:
        return _Sheets(self._s)

    def get(self, spreadsheetId: str, fields: str, ranges: list[str] | None = None) -> FakeRequest:
        def run() -> Any:
            ss = self._s.spreadsheet(spreadsheetId)
            if fields.startswith("spreadsheetId"):  # gsuite_sheets.Sheets.open_by_key
                return {
                    "spreadsheetId": ss.id,
                    "properties": {"title": ss.title, "locale": "en_US", "timeZone": "UTC"},
                    "sheets": [
                        {"properties": {"sheetId": ws.id, "title": ws.title, "index": i}}
                        for i, ws in enumerate(ss.worksheets)
                    ],
                }
            if fields == "sheets.properties(sheetId,title)":
                return {
                    "sheets": [
                        {"properties": {"sheetId": ws.id, "title": ws.title}}
                        for ws in ss.worksheets
                    ]
                }
            return ss.get_metadata(ranges, fields)

        return FakeRequest("GET", run)

    def create(self, body: dict[str, Any]) -> FakeRequest:
        def run() -> Any:
            ss = self._s.client.create(body["properties"]["title"], None)
            ss.seed("Sheet1")
            return {"spreadsheetId": ss.id}

        return FakeRequest("POST", run)

    def batchUpdate(self, spreadsheetId: str, body: dict[str, Any]) -> FakeRequest:
        def run() -> Any:
            ss = self._s.spreadsheet(spreadsheetId)
            replies: list[dict[str, Any]] = []
            for request in body.get("requests", []):
                # The emulator manages tabs through methods, not batchUpdate requests
                if "addSheet" in request:
                    props = request["addSheet"]["properties"]
                    grid = props.get("gridProperties", {})
                    ws = ss.add_worksheet(
                        props["title"],
                        grid.get("rowCount", 1000),
                        grid.get("columnCount", 26),
                        props.get("index"),
                    )
                    replies.append(
                        {
                            "addSheet": {
                                "properties": {"sheetId": ws.id, "title": ws.title, "index": 0}
                            }
                        }
                    )
                elif "deleteSheet" in request:
                    sheet_id = request["deleteSheet"]["sheetId"]
                    ss.delete_worksheet(next(w.title for w in ss.worksheets if w.id == sheet_id))
                    replies.append({})
                elif "updateSheetProperties" in request and "title" in request[
                    "updateSheetProperties"
                ]["fields"].split(","):
                    props = request["updateSheetProperties"]["properties"]
                    ws = next(w for w in ss.worksheets if w.id == props["sheetId"])
                    ws._title = props["title"]
                    replies.append({})
                else:
                    ss.batch_update({"requests": [request]})
                    if "addProtectedRange" in request:
                        replies.append({"addProtectedRange": {"protectedRange": ss._protected[-1]}})
                    elif "addNamedRange" in request:
                        replies.append({"addNamedRange": {"namedRange": ss._named[-1]}})
                    else:
                        replies.append({})
            return {"replies": replies}

        return FakeRequest("POST", run)


class _Files:
    def __init__(self, service: FakeGoogleService) -> None:
        self._s = service

    def list(self, q: str = "", **params: Any) -> FakeRequest:
        def run() -> Any:
            name = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
            title = _unescape(name.group(1)) if name else None
            files = self._s.client.list_spreadsheet_files(title, None)
            if params.get("pageSize") == 1:
                files = files[:1]
            return {"files": files}

        return FakeRequest("GET", run)

    def update(self, fileId: str, **params: Any) -> FakeRequest:
        return FakeRequest("PATCH", lambda: {"id": fileId})

    def delete(self, fileId: str, **params: Any) -> FakeRequest:
        return FakeRequest("DELETE", lambda: self._s.client.del_spreadsheet(fileId))

    def copy(self, fileId: str, body: dict[str, Any], **params: Any) -> FakeRequest:
        def run() -> Any:
            clone = self._s.client.copy(fileId, body.get("name"), False, None)
            return {"id": clone.id, "name": clone.title}

        return FakeRequest("POST", run)

    def export(self, fileId: str, mimeType: str) -> FakeRequest:
        return FakeRequest("GET", lambda: self._s.spreadsheet(fileId).export(mimeType))


class _Permissions:
    def __init__(self, service: FakeGoogleService) -> None:
        self._s = service

    def create(self, fileId: str, body: dict[str, Any], **params: Any) -> FakeRequest:
        def run() -> Any:
            return self._s.spreadsheet(fileId).share(
                body.get("emailAddress") or body.get("domain") or "",
                body["type"],
                body["role"],
                params.get("sendNotificationEmail", False),
                params.get("emailMessage"),
                not body.get("allowFileDiscovery", True),
            )

        return FakeRequest("POST", run)

    def list(self, fileId: str, **params: Any) -> FakeRequest:
        return FakeRequest(
            "GET", lambda: {"permissions": self._s.spreadsheet(fileId).list_permissions()}
        )

    def delete(self, fileId: str, permissionId: str, **params: Any) -> FakeRequest:
        def run() -> Any:
            ss = self._s.spreadsheet(fileId)
            ss.permissions = [p for p in ss.permissions if p["id"] != permissionId]

        return FakeRequest("DELETE", run)


class FakeGoogleService:
    """Sheets v4 + Drive v3 service over an ``InMemoryClient`` (use it for both)."""

    def __init__(self, client: InMemoryClient) -> None:
        self.client = client

    def spreadsheet(self, spreadsheet_id: str) -> InMemorySpreadsheet:
        return self.client.spreadsheet_by_key(spreadsheet_id)

    # Sheets API
    def spreadsheets(self) -> _Spreadsheets:
        return _Spreadsheets(self)

    # Drive API
    def files(self) -> _Files:
        return _Files(self)

    def permissions(self) -> _Permissions:
        return _Permissions(self)


def _trim(rows: list[list[str]]) -> list[list[str]]:
    rows = [list(r) for r in rows]
    while rows and all(c == "" for c in rows[-1]):
        rows.pop()
    for row in rows:
        while row and row[-1] == "":
            row.pop()
    return rows


def fake_sheets(client: InMemoryClient, **options: Any) -> Any:
    """A real ``gsuite_sheets.Sheets`` whose Google services are faked over ``client``.

    Use it to test code written against the public API without network::

        backend = InMemoryBackend()
        backend.add_spreadsheet("Budget", {"Data": [["name", "total"]]})
        sheets = fake_sheets(backend.client)
        ws = sheets.open("Budget").worksheet("Data")
    """
    from unittest.mock import Mock

    from gsuite_sheets.client import Sheets

    sheets = Sheets(Mock(), **options)
    fake = FakeGoogleService(client)
    sheets._sheets_service = fake
    sheets._drive_service = fake
    return sheets


def adapter_client(client: InMemoryClient) -> Any:
    """A ``GoogleApiClient`` (the real adapter) whose requests hit ``client``."""
    from gsuite_sheets.engine_adapter import GoogleApiClient

    return GoogleApiClient(fake_sheets(client))
