"""Async Sheets API: AsyncSheets / AsyncSpreadsheet / AsyncWorksheet.

Mirrors the sync API for reading and writing values, streaming, tables and
typed rows (the operations GSpreadManager's async engine supports).
Formatting, validation, charts and other structure changes are sync-only.
Requests go through gsuite_core.aio, so retries, rate limits and errors are
the suite's.

Example:
    async with AsyncSheets(auth) as sheets:
        ws = (await sheets.open("Budget")).worksheet("Data")
        await ws.append_row(["Ana", 10])
        async for record in ws.iter_records():
            ...

Requires ``pip install "gsuite-sdk[async]"``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from gsuite_core.aio import AsyncGoogleClient
from gsuite_sheets.a1 import a1


class AsyncSheets:
    """Entry point: open, create, copy and delete spreadsheets.

    Args:
        auth: GoogleAuth (OAuth or service account) or google-auth credentials
        timeout: Seconds per request (default: GSUITE_REQUEST_TIMEOUT)
        batch_cell_limit: Split big writes into requests of at most this many cells
        transport: httpx transport (tests)
    """

    def __init__(
        self,
        auth: Any,
        *,
        timeout: float | None = None,
        batch_cell_limit: int | None = 50_000,
        transport: Any = None,
    ) -> None:
        from gsuite_sheets.engine_async_adapter import AsyncGoogleApiClient

        self._http = AsyncGoogleClient(auth, timeout=timeout, transport=transport)
        self._port = AsyncGoogleApiClient(self._http)
        self._batch_cell_limit = batch_cell_limit
        self._managers: dict[str, Any] = {}

    async def __aenter__(self) -> AsyncSheets:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    def _manager(self, spreadsheet_id: str) -> Any:
        if spreadsheet_id not in self._managers:
            from gsuite_sheets.engine.async_facade import AsyncSheetManager

            self._managers[spreadsheet_id] = AsyncSheetManager(
                key=spreadsheet_id,
                sheets_client=self._port,
                batch_cell_limit=self._batch_cell_limit,
            )
        return self._managers[spreadsheet_id]

    def _forget(self, spreadsheet_id: str) -> None:
        self._port.forget(spreadsheet_id)

    async def open(self, title: str) -> AsyncSpreadsheet:
        """Open by title (searches Drive)."""
        return AsyncSpreadsheet(self, await self._port.open(title))

    async def open_by_key(self, key: str) -> AsyncSpreadsheet:
        """Open by ID."""
        return AsyncSpreadsheet(self, await self._port.open_by_key(key))

    async def open_by_url(self, url: str) -> AsyncSpreadsheet:
        """Open by URL."""
        from gsuite_sheets.engine.domain.values import SpreadsheetId

        return await self.open_by_key(SpreadsheetId.from_url(url).value)

    async def create(self, title: str, folder_id: str | None = None) -> AsyncSpreadsheet:
        """Create a spreadsheet."""
        return AsyncSpreadsheet(self, await self._port.create(title, folder_id))

    async def copy(
        self,
        spreadsheet_id: str,
        title: str | None = None,
        copy_permissions: bool = False,
        folder_id: str | None = None,
    ) -> AsyncSpreadsheet:
        """Copy a spreadsheet (optionally with its sharing, except ownership)."""
        copied = await self._port.copy(spreadsheet_id, title, copy_permissions, folder_id)
        return AsyncSpreadsheet(self, copied)

    async def delete(self, spreadsheet_id: str) -> None:
        """Delete a spreadsheet permanently."""
        await self._port.del_spreadsheet(spreadsheet_id)
        self._managers.pop(spreadsheet_id, None)

    async def list_spreadsheets(self, title: str | None = None) -> list[dict[str, Any]]:
        """Spreadsheets visible to the user ({id, name})."""
        return list(await self._port.list_spreadsheet_files(title, None))


class AsyncSpreadsheet:
    """A spreadsheet: its tabs and document-level operations."""

    def __init__(self, sheets: AsyncSheets, port: Any) -> None:
        self._sheets = sheets
        self._port = port
        self.id: str = port.id
        self.title: str = getattr(port, "title", "")

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.id}"

    @property
    def worksheets(self) -> list[AsyncWorksheet]:
        """Tabs, as loaded when the spreadsheet was opened (or last changed here)."""
        return [AsyncWorksheet(self, title, sheet_id) for title, sheet_id in self._port.tabs]

    @property
    def sheet1(self) -> AsyncWorksheet | None:
        tabs = self.worksheets
        return tabs[0] if tabs else None

    def worksheet(self, title: str) -> AsyncWorksheet | None:
        """Tab by title (no request)."""
        return next((ws for ws in self.worksheets if ws.title == title), None)

    async def add_worksheet(self, title: str, rows: int = 1000, cols: int = 26) -> AsyncWorksheet:
        port_ws = await self._port.add_worksheet(title, rows, cols, None)
        return AsyncWorksheet(self, port_ws.title, port_ws.id)

    async def worksheet_or_create(
        self, title: str, rows: int = 100, cols: int = 26
    ) -> AsyncWorksheet:
        return self.worksheet(title) or await self.add_worksheet(title, rows, cols)

    async def del_worksheet(self, worksheet: AsyncWorksheet) -> None:
        await self._port.delete_worksheet(worksheet.title)

    async def export(self, format: str = "pdf") -> bytes:
        """pdf, xlsx, ods, csv, tsv (first sheet) or html (zip)."""
        from gsuite_sheets.engine.domain.export import ExportFormat

        formats = {
            "pdf": ExportFormat.PDF,
            "xlsx": ExportFormat.EXCEL,
            "ods": ExportFormat.ODS,
            "csv": ExportFormat.CSV,
            "tsv": ExportFormat.TSV,
            "html": ExportFormat.HTML,
        }
        content: bytes = await self._port.export(str(formats.get(format.lower(), format)))
        return content

    async def share(self, email: str, role: str = "reader", notify: bool = True) -> None:
        await self._port.share(email, "user", role, notify, None, False)

    async def list_permissions(self) -> list[dict[str, Any]]:
        return list(await self._port.list_permissions())

    async def remove_permission(self, value: str, role: str = "any") -> list[str]:
        return list(await self._port.remove_permissions(value, role))

    async def _update_properties(self, properties: dict[str, Any]) -> None:
        await self._port.batch_update(
            {
                "requests": [
                    {
                        "updateSpreadsheetProperties": {
                            "properties": properties,
                            "fields": ",".join(properties),
                        }
                    }
                ]
            }
        )

    async def update_title(self, title: str) -> None:
        await self._update_properties({"title": title})
        self.title = title

    async def update_locale(self, locale: str) -> None:
        await self._update_properties({"locale": locale})

    async def update_timezone(self, timezone: str) -> None:
        await self._update_properties({"timeZone": timezone})


class AsyncWorksheet:
    """A tab. Values, streaming, tables and typed rows, async."""

    def __init__(self, spreadsheet: AsyncSpreadsheet, title: str, sheet_id: int) -> None:
        self._spreadsheet = spreadsheet
        self.title = title
        self.id = sheet_id

    async def _ctx(self) -> Any:
        manager = self._spreadsheet._sheets._manager(self._spreadsheet.id)
        return await manager.worksheet(self.title)

    def _port(self) -> Any:
        return self._spreadsheet._port.worksheet(self.title)

    # ---- values ----

    async def get(self, range: str = "A1", value_render: str | None = None) -> list[list[Any]]:
        data = await self._spreadsheet._port.values_get(a1(self.title, range), value_render)
        values: list[list[Any]] = data.get("values", [])
        return values

    async def get_all_values(self, value_render: str | None = None) -> list[list[Any]]:
        values: list[list[Any]] = await self._port().get_all_values(value_render)
        return values

    async def get_all_records(self, head: int = 1) -> list[dict[str, Any]]:
        values = await self.get_all_values()
        if len(values) < head:
            return []
        headers = values[head - 1]
        return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[head:]]

    async def update(
        self, range: str, values: list[list[Any]], value_input: str = "USER_ENTERED"
    ) -> Any:
        return await self._port().update(values, value_input, range)

    async def update_cell(self, row: int, col: int, value: Any) -> None:
        await (await self._ctx()).update_cell(row, col, value)

    async def update_row(
        self, row: int, values: list[Any], start_column: int | None = None
    ) -> None:
        await (await self._ctx()).update_row(row, values, start_column=start_column)

    async def append_row(self, values: list[Any], value_input: str = "USER_ENTERED") -> Any:
        return await self.append_rows([values], value_input)

    async def append_rows(self, rows: list[list[Any]], value_input: str = "USER_ENTERED") -> Any:
        return await self._port().append_rows(rows, value_input)

    async def batch_update(
        self, data: list[dict[str, Any]], value_input: str = "USER_ENTERED"
    ) -> None:
        await (await self._ctx()).batch_update(data, value_input)

    async def clear(self, range: str | list[str] | None = None) -> None:
        await (await self._ctx()).clear(range)

    async def find(self, query: str, case_sensitive: bool = True) -> Any:
        return await (await self._ctx()).find(query, case_sensitive)

    async def replace(
        self,
        find: str,
        replacement: str,
        *,
        match_case: bool = False,
        match_entire_cell: bool = False,
        regex: bool = False,
    ) -> int:
        result = await (await self._ctx()).find_replace(
            find,
            replacement,
            match_case=match_case,
            match_entire_cell=match_entire_cell,
            search_by_regex=regex,
        )
        return int(result.get("occurrencesChanged", 0)) if isinstance(result, dict) else 0

    async def import_csv(self, source: Any, *, clear: bool = True, delimiter: str = ",") -> Any:
        return await (await self._ctx()).import_csv(source, clear=clear, delimiter=delimiter)

    async def copy_to(self, destination_spreadsheet_id: str) -> Any:
        return await (await self._ctx()).copy_to(destination_spreadsheet_id)

    # ---- streaming ----

    async def iter_rows(self, page_size: int = 1000, skiprows: int = 0) -> AsyncIterator[list[str]]:
        async for row in (await self._ctx()).iter_rows(page_size=page_size, skiprows=skiprows):
            yield row

    async def iter_records(self, page_size: int = 1000) -> AsyncIterator[dict[str, str]]:
        async for record in (await self._ctx()).iter_records(page_size=page_size):
            yield record

    async def iter_as(self, model: type, page_size: int = 1000) -> AsyncIterator[Any]:
        async for item in (await self._ctx()).iter_as(model, page_size=page_size):
            yield item

    # ---- tables and typed rows ----

    async def upsert(
        self, rows: list[dict[str, Any]] | list[list[Any]], key: str
    ) -> dict[str, int]:
        return dict(await (await self._ctx()).upsert(rows, key))

    async def update_where(self, where: Any, updates: dict[str, Any]) -> int:
        return int(await (await self._ctx()).update_where(where, updates))

    async def delete_where(self, where: Any) -> int:
        return int(await (await self._ctx()).delete_where(where))

    async def ensure_schema(
        self, model: type, *, create: bool = True, strict: bool = False
    ) -> dict[str, Any]:
        return dict(await (await self._ctx()).ensure_schema(model, create=create, strict=strict))

    async def read_as(self, model: type, skiprows: int = 0) -> list[Any]:
        return list(await (await self._ctx()).read_as(model, skiprows=skiprows))

    async def append_models(self, models: list[Any]) -> Any:
        return await (await self._ctx()).append_models(models)

    async def write_models(
        self, models: list[Any], include_header: bool = True, clear: bool = True
    ) -> Any:
        return await (await self._ctx()).write_models(
            models, include_header=include_header, clear=clear
        )

    async def upsert_models(self, models: list[Any], key: str) -> dict[str, int]:
        return dict(await (await self._ctx()).upsert_models(models, key))
