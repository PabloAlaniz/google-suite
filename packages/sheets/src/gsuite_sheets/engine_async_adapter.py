"""The engine's async ports over gsuite_core.aio (Sheets v4 / Drive v3 REST).

Async counterpart of ``engine_adapter``: same behavior and the same request
builders (titles quoted, Drive queries escaped, range() returns the whole
rectangle, domain shares keep the domain), sent through ``AsyncGoogleClient``
so retries, rate limits and errors are the suite's.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from gsuite_core.aio import AsyncGoogleClient
from gsuite_core.exceptions import NotFoundError
from gsuite_sheets.a1 import a1
from gsuite_sheets.engine.config import DEFAULT_VALUE_INPUT_OPTION
from gsuite_sheets.engine.domain.errors import (
    GSpreadManagerError,
    SpreadsheetNotFoundError,
    WorksheetNotFoundError,
)
from gsuite_sheets.engine.domain.values import rowcol_to_a1
from gsuite_sheets.engine_adapter import (
    Cell,
    _qualify,
    _rectangular,
    cells_in_range,
    find_cell,
    format_body,
    freeze_body,
    merge_body,
    share_request,
    spreadsheet_query,
)

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
ALL_DRIVES = {"supportsAllDrives": "true"}


class AsyncGoogleApiClient:
    """``AsyncClientPort`` over an ``AsyncGoogleClient``."""

    def __init__(self, http: AsyncGoogleClient) -> None:
        self._http = http
        self._open: dict[str, AsyncGoogleApiSpreadsheet] = {}

    def forget(self, spreadsheet_id: str) -> None:
        """Drop a spreadsheet from the open cache (its tabs changed elsewhere)."""
        self._open = {k: v for k, v in self._open.items() if v.id != spreadsheet_id}

    async def open(self, doc_name: str) -> AsyncGoogleApiSpreadsheet:
        """Open by title (Drive search; quotes in the title are escaped)."""
        if doc_name not in self._open:
            response = await self._http.json(
                "GET",
                DRIVE_FILES,
                service="sheets",
                resource_type="spreadsheet",
                resource_id=doc_name,
                params={
                    "q": spreadsheet_query(doc_name, None),
                    "fields": "files(id,name)",
                    "pageSize": 1,
                    "includeItemsFromAllDrives": "true",
                    **ALL_DRIVES,
                },
            )
            files = response.get("files", [])
            if not files:
                raise SpreadsheetNotFoundError(f"No se encontró el documento '{doc_name}'.")
            self._open[doc_name] = await self.open_by_key(files[0]["id"])
        return self._open[doc_name]

    async def open_by_key(self, key: str) -> AsyncGoogleApiSpreadsheet:
        """Open by ID, loading the (title, sheetId) of each tab."""
        if key not in self._open:
            try:
                meta = await self._http.json(
                    "GET",
                    f"{SHEETS_API}/{key}",
                    service="sheets",
                    resource_type="spreadsheet",
                    resource_id=key,
                    params={"fields": "properties(title),sheets.properties(sheetId,title)"},
                )
            except NotFoundError as exc:
                raise SpreadsheetNotFoundError(
                    f"No se encontró el documento con key '{key}'."
                ) from exc
            tabs = [
                (s["properties"]["title"], s["properties"]["sheetId"])
                for s in meta.get("sheets", [])
            ]
            self._open[key] = AsyncGoogleApiSpreadsheet(
                self._http, key, tabs, meta.get("properties", {}).get("title", "")
            )
        return self._open[key]

    async def create(self, title: str, folder_id: str | None) -> AsyncGoogleApiSpreadsheet:
        """Create a spreadsheet (moved into ``folder_id`` if given) and return it opened."""
        created = await self._http.json(
            "POST", SHEETS_API, service="sheets", json={"properties": {"title": title}}
        )
        key = created["spreadsheetId"]
        if folder_id is not None:
            await self._http.json(
                "PATCH",
                f"{DRIVE_FILES}/{key}",
                service="sheets",
                params={"addParents": folder_id, "removeParents": "root", **ALL_DRIVES},
                json={},
            )
        return await self.open_by_key(key)

    async def del_spreadsheet(self, file_id: str) -> None:
        """Delete a spreadsheet (Drive)."""
        await self._http.request(
            "DELETE",
            f"{DRIVE_FILES}/{file_id}",
            service="sheets",
            resource_type="spreadsheet",
            resource_id=file_id,
            params=ALL_DRIVES,
        )
        self.forget(file_id)

    async def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> AsyncGoogleApiSpreadsheet:
        """Copy a spreadsheet, optionally with its permissions (ownership excluded)."""
        body: dict[str, Any] = {}
        if title is not None:
            body["name"] = title
        if folder_id is not None:
            body["parents"] = [folder_id]
        copied = await self._http.json(
            "POST",
            f"{DRIVE_FILES}/{file_id}/copy",
            service="sheets",
            resource_type="spreadsheet",
            resource_id=file_id,
            params=ALL_DRIVES,
            json=body,
        )
        if copy_permissions:
            source = AsyncGoogleApiSpreadsheet(self._http, file_id, [])
            target = AsyncGoogleApiSpreadsheet(self._http, copied["id"], [])
            for perm in await source.list_permissions():
                if perm.get("role") == "owner":
                    continue
                await target.share(
                    perm.get("emailAddress") or perm.get("domain") or "",
                    perm.get("type", "user"),
                    perm.get("role", "reader"),
                    notify=False,
                    email_message=None,
                    with_link=False,
                )
        return await self.open_by_key(copied["id"])

    async def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Spreadsheets visible to the user, following every page."""
        return [
            item
            async for item in self._http.paginate(
                DRIVE_FILES,
                "files",
                service="sheets",
                page_size_param="pageSize",
                max_page_size=1000,
                params={
                    "q": spreadsheet_query(title, folder_id),
                    "fields": "nextPageToken,files(id,name)",
                    "includeItemsFromAllDrives": "true",
                    **ALL_DRIVES,
                },
            )
        ]


class AsyncGoogleApiSpreadsheet:
    """``AsyncSpreadsheetPort`` for one spreadsheet ID."""

    def __init__(
        self,
        http: AsyncGoogleClient,
        spreadsheet_id: str,
        tabs: list[tuple[str, int]],
        title: str = "",
    ) -> None:
        self._http = http
        self.id = spreadsheet_id
        self.title = title
        self._tabs = tabs

    @property
    def tabs(self) -> list[tuple[str, int]]:
        """(title, sheetId) of each tab, as last loaded."""
        return list(self._tabs)

    def _sheet_id(self, title: str) -> int:
        for name, sheet_id in self._tabs:
            if name == title:
                return sheet_id
        raise WorksheetNotFoundError(f"No existe la hoja '{title}'.")

    @property
    def sheet1(self) -> AsyncGoogleApiWorksheet:
        """First tab."""
        if not self._tabs:
            raise GSpreadManagerError("El documento no tiene hojas.")
        title, sheet_id = self._tabs[0]
        return AsyncGoogleApiWorksheet(self, title, sheet_id)

    def worksheet(self, name: str) -> AsyncGoogleApiWorksheet:
        """Tab by title."""
        return AsyncGoogleApiWorksheet(self, name, self._sheet_id(name))

    async def _json(self, method: str, url: str, **kwargs: Any) -> Any:
        return await self._http.json(
            method,
            url,
            service="sheets",
            resource_type="spreadsheet",
            resource_id=self.id,
            **kwargs,
        )

    def _values_url(self, a1_range: str, suffix: str = "") -> str:
        return f"{SHEETS_API}/{self.id}/values/{quote(a1_range, safe='')}{suffix}"

    async def add_worksheet(
        self, title: str, rows: int, cols: int, index: int | None
    ) -> AsyncGoogleApiWorksheet:
        """Add a tab and return it."""
        props: dict[str, Any] = {
            "title": title,
            "gridProperties": {"rowCount": rows, "columnCount": cols},
        }
        if index is not None:
            props["index"] = index
        reply = await self.batch_update({"requests": [{"addSheet": {"properties": props}}]})
        sheet_id = reply["replies"][0]["addSheet"]["properties"]["sheetId"]
        self._tabs.append((title, sheet_id))
        return AsyncGoogleApiWorksheet(self, title, sheet_id)

    async def delete_worksheet(self, title: str) -> None:
        """Delete a tab by title."""
        sheet_id = self._sheet_id(title)
        await self.batch_update({"requests": [{"deleteSheet": {"sheetId": sheet_id}}]})
        self._tabs = [(n, sid) for (n, sid) in self._tabs if n != title]

    async def values_get(self, a1_range: str, value_render_option: str | None = None) -> Any:
        """``spreadsheets.values.get``."""
        params = {"valueRenderOption": value_render_option} if value_render_option else None
        return await self._json("GET", self._values_url(a1_range), params=params)

    async def values_append(
        self, a1_range: str, params: dict[str, Any], body: dict[str, Any]
    ) -> Any:
        """``spreadsheets.values.append``."""
        return await self._json(
            "POST", self._values_url(a1_range, ":append"), params=params, json=body
        )

    async def batch_update(self, body: dict[str, Any]) -> Any:
        """``spreadsheets.batchUpdate``."""
        return await self._json("POST", f"{SHEETS_API}/{self.id}:batchUpdate", json=body)

    async def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """``spreadsheets.get`` limited to ``ranges`` / ``fields``."""
        params: dict[str, Any] = {"fields": fields}
        if ranges is not None:
            params["ranges"] = ranges
        result: dict[str, Any] = await self._json("GET", f"{SHEETS_API}/{self.id}", params=params)
        return result

    async def export(self, mime_type: str) -> bytes:
        """Export the spreadsheet (Drive ``files.export``)."""
        response = await self._http.request(
            "GET",
            f"{DRIVE_FILES}/{self.id}/export",
            service="sheets",
            resource_type="spreadsheet",
            resource_id=self.id,
            params={"mimeType": mime_type},
        )
        content: bytes = response.content
        return content

    async def share(
        self,
        email_address: str,
        perm_type: str,
        role: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Grant a permission (Drive ``permissions.create``)."""
        body, params = share_request(
            email_address, perm_type, role, notify, email_message, with_link
        )
        params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
        return await self._json(
            "POST",
            f"{DRIVE_FILES}/{self.id}/permissions",
            params={**params, **ALL_DRIVES},
            json=body,
        )

    async def list_permissions(self) -> list[dict[str, Any]]:
        """All permissions (Drive ``permissions.list``)."""
        return [
            item
            async for item in self._http.paginate(
                f"{DRIVE_FILES}/{self.id}/permissions",
                "permissions",
                service="sheets",
                page_size_param="pageSize",
                max_page_size=100,
                params={
                    "fields": "nextPageToken,permissions(id,type,role,emailAddress,domain)",
                    **ALL_DRIVES,
                },
            )
        ]

    async def remove_permissions(self, value: str, role: str) -> list[str]:
        """Remove the permissions of ``value`` (email or domain) with ``role`` ("any" = all)."""
        removed: list[str] = []
        for perm in await self.list_permissions():
            matches_value = value in (perm.get("emailAddress"), perm.get("domain"))
            matches_role = role == "any" or perm.get("role") == role
            if matches_value and matches_role:
                await self._http.request(
                    "DELETE",
                    f"{DRIVE_FILES}/{self.id}/permissions/{perm['id']}",
                    service="sheets",
                    resource_type="permission",
                    resource_id=perm["id"],
                    params=ALL_DRIVES,
                )
                removed.append(perm["id"])
        return removed


class AsyncGoogleApiWorksheet:
    """``AsyncWorksheetPort`` for one tab."""

    def __init__(self, spreadsheet: AsyncGoogleApiSpreadsheet, title: str, sheet_id: int) -> None:
        self._parent = spreadsheet
        self._title = title
        self._sheet_id = sheet_id

    @property
    def id(self) -> int:
        """Numeric sheetId."""
        return self._sheet_id

    @property
    def title(self) -> str:
        """Tab title."""
        return self._title

    @property
    def spreadsheet(self) -> AsyncGoogleApiSpreadsheet:
        """Spreadsheet this tab belongs to."""
        return self._parent

    async def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Every row of the tab, padded to a rectangle."""
        data = await self._parent.values_get(a1(self._title), value_render_option)
        rows: list[list[str]] = data.get("values", [])
        return _rectangular(rows)

    async def _write(self, a1_range: str, values: list[list[Any]], value_input_option: str) -> Any:
        return await self._parent._json(
            "PUT",
            self._parent._values_url(a1_range),
            params={"valueInputOption": value_input_option},
            json={"values": values},
        )

    async def update_cell(self, row: int, col: int, value: Any) -> None:
        """Write one cell (1-based)."""
        await self._write(
            a1(self._title, rowcol_to_a1(row, col)), [[value]], DEFAULT_VALUE_INPUT_OPTION
        )

    async def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Write ``values`` from A1, or from ``range_name`` (its top-left cell)."""
        target = a1(self._title) if range_name is None else _qualify(self._title, range_name)
        return await self._write(target, values, value_input_option)

    async def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Append rows after the last one with data."""
        return await self._parent.values_append(
            a1(self._title),
            {"valueInputOption": value_input_option, "insertDataOption": "INSERT_ROWS"},
            {"values": data},
        )

    async def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Write several ranges in one request."""
        data = [{**item, "range": _qualify(self._title, item["range"])} for item in range_data]
        await self._parent._json(
            "POST",
            f"{SHEETS_API}/{self._parent.id}/values:batchUpdate",
            json={"valueInputOption": value_input_option, "data": data},
        )

    async def clear(self) -> None:
        """Clear every value of the tab (formatting is kept)."""
        await self._parent._json(
            "POST", self._parent._values_url(a1(self._title), ":clear"), json={}
        )

    async def batch_clear(self, ranges: list[str]) -> None:
        """Clear several ranges."""
        await self._parent._json(
            "POST",
            f"{SHEETS_API}/{self._parent.id}/values:batchClear",
            json={"ranges": [_qualify(self._title, r) for r in ranges]},
        )

    async def col_values(self, col: int) -> list[Any]:
        """Values of a column (1-based)."""
        return [row[col - 1] if col - 1 < len(row) else "" for row in await self.get_all_values()]

    async def row_values(self, row: int) -> list[Any]:
        """Values of a row (1-based)."""
        values = await self.get_all_values()
        return values[row - 1] if 0 < row <= len(values) else []

    async def find(self, query: str, case_sensitive: bool) -> Cell | None:
        """First cell whose value equals ``query``."""
        return find_cell(await self.get_all_values(), query, case_sensitive)

    async def range(self, name: str) -> list[Cell]:
        """Every cell of an A1 range, empty ones included."""
        data = await self._parent.values_get(_qualify(self._title, name))
        return cells_in_range(name, self._sheet_id, data.get("values", []))

    async def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Apply a (serialized) CellFormat to one or more ranges."""
        return await self._parent.batch_update(format_body(self._sheet_id, ranges, cell_format))

    async def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Freeze rows and/or columns."""
        return await self._parent.batch_update(freeze_body(self._sheet_id, rows, cols))

    async def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Merge the cells of a range."""
        return await self._parent.batch_update(merge_body(self._sheet_id, range_name, merge_type))

    async def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copy this tab into another spreadsheet (``sheets.copyTo``)."""
        return await self._parent._json(
            "POST",
            f"{SHEETS_API}/{self._parent.id}/sheets/{self._sheet_id}:copyTo",
            json={"destinationSpreadsheetId": destination_spreadsheet_id},
        )
