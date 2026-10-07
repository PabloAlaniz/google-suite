"""API async 3.0: ``AsyncSheetManager`` + ``AsyncWorksheetContext``.

Espejo async de la facade síncrona sobre los puertos async (cliente nativo httpx; extra
``[async]``). Cubre el flujo de **datos**: lectura (list/dict/render/numericise), escritura
(append/update/batch con chunking), streaming (``iter_*``), la hoja como tabla
(upsert/where), modelos tipados (dataclasses/Pydantic, ``ensure_schema``), import CSV,
find/replace, copy_to y las operaciones de documento (Drive, permisos, propiedades,
export). El formato/validación/charts siguen, por ahora, solo en la API síncrona.

Reutiliza toda la lógica pura (numericise, schema/codecs, batching, planners de tabla,
CSV); solo el IO cambia de transporte. Para testear sin red:
``gspreadmanager.testing.AsyncInMemoryBackend``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .application.row_model_service import RowModelService, schema_drift
from .application.table_service import (
    Where,
    plan_delete_requests,
    plan_update_where,
    plan_upsert,
    require_header,
)
from .config import DEFAULT_VALUE_INPUT_OPTION
from .domain.batching import DEFAULT_MAX_CELLS_PER_REQUEST, split_range_data, split_rows
from .domain.csv_data import rows_from_csv
from .domain.errors import GSpreadManagerError, SchemaError, WorksheetNotFoundError
from .domain.export import ExportFormat
from .domain.numericise import numericise_all, numericise_records
from .domain.values import SpreadsheetId
from .facade import _resolve_render
from .infrastructure.async_rate_limit import AsyncTokenBucketRateLimiter
from .infrastructure.auth import build_credentials
from .infrastructure.native import DEFAULT_HTTP_TIMEOUT, AsyncSheetsApiClient
from .infrastructure.native.async_http import build_async_session
from .ports.async_sheets import AsyncClientPort, AsyncSpreadsheetPort, AsyncWorksheetPort
from .ports.rate_limit import AsyncRateLimiter
from .retry import retry_on_rate_limit_async


class AsyncSheetManager:
    """Gestor async de un documento de Google Sheets (siempre backend nativo).

    Ejemplo:
        async with AsyncSheetManager("MiDoc", json_google_file="creds.json") as mgr:
            ws = await mgr.worksheet("Hoja1")
            datos = await ws.read(output_format="dict")
    """

    def __init__(
        self,
        doc_name: str | None = None,
        json_google_file: str | None = None,
        *,
        key: str | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        credentials: Any = None,
        service_account_info: dict[str, Any] | None = None,
        use_adc: bool = False,
        http_timeout: float | None = DEFAULT_HTTP_TIMEOUT,
        sheets_client: AsyncClientPort | None = None,
        rate_limit: float | None = None,
        rate_limit_burst: float | None = None,
        batch_cell_limit: int | None = DEFAULT_MAX_CELLS_PER_REQUEST,
    ) -> None:
        """Configura la autenticación y el cliente async (nativo sobre httpx).

        Mismos parámetros de identidad/credenciales/robustez que ``SheetManager``; no hay
        ``backend`` (async solo existe el nativo) ni ``cache`` (pendiente). El retry y el
        rate limiting son cooperativos (``asyncio.sleep``). ``sheets_client`` inyecta un
        ``AsyncClientPort`` propio (ej. ``gspreadmanager.testing.AsyncInMemoryBackend``).
        """
        if doc_name is None and key is None:
            raise GSpreadManagerError("Indicá 'doc_name' o 'key' al crear AsyncSheetManager.")
        self.doc_name = doc_name
        self._key = key
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.batch_cell_limit = batch_cell_limit
        self._rate_limiter: AsyncRateLimiter | None = (
            AsyncTokenBucketRateLimiter(rate_limit, rate_limit_burst)
            if rate_limit is not None
            else None
        )
        self._session: Any = None
        if sheets_client is not None:
            self._client: AsyncClientPort = sheets_client
        else:
            creds = build_credentials(
                credentials=credentials,
                service_account_info=service_account_info,
                json_google_file=json_google_file,
                use_adc=use_adc,
            )
            self._session = build_async_session(creds, timeout=http_timeout)
            self._client = AsyncSheetsApiClient(self._session)
        self._rows = RowModelService()

    async def __aenter__(self) -> AsyncSheetManager:
        """Permite usar el gestor como async context manager."""
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Cierra la sesión httpx subyacente (si la construyó este gestor)."""
        await self.aclose()

    async def aclose(self) -> None:
        """Cierra la sesión httpx (no-op con un ``sheets_client`` inyectado)."""
        if self._session is not None:
            await self._session.__aexit__(None, None, None)

    @classmethod
    def open_by_key(
        cls, key: str, json_google_file: str | None = None, **kwargs: Any
    ) -> AsyncSheetManager:
        """Crea un gestor para el documento con ``key`` (id de Drive)."""
        return cls(key=key, json_google_file=json_google_file, **kwargs)

    @classmethod
    def open_by_url(
        cls, url: str, json_google_file: str | None = None, **kwargs: Any
    ) -> AsyncSheetManager:
        """Crea un gestor para el documento de una URL de Google Sheets."""
        return cls(
            key=SpreadsheetId.from_url(url).value, json_google_file=json_google_file, **kwargs
        )

    async def _spreadsheet(self) -> AsyncSpreadsheetPort:
        if self.doc_name is not None:
            return await self._client.open(self.doc_name)
        assert self._key is not None  # garantizado por __init__  # noqa: S101  # nosec B101
        return await self._client.open_by_key(self._key)

    @retry_on_rate_limit_async
    async def worksheet(self, tab_name: str | None = None) -> AsyncWorksheetContext:
        """Devuelve un handle inmutable a una pestaña (la primera si ``tab_name`` es None)."""
        spreadsheet = await self._spreadsheet()
        ws = spreadsheet.worksheet(tab_name) if tab_name else spreadsheet.sheet1
        return AsyncWorksheetContext(ws, self)

    @retry_on_rate_limit_async
    async def create_sheet(
        self, title: str, rows: int = 100, cols: int = 26, index: int | None = None
    ) -> AsyncWorksheetContext:
        """Crea una nueva pestaña y devuelve su handle."""
        spreadsheet = await self._spreadsheet()
        ws = await spreadsheet.add_worksheet(title, rows, cols, index)
        return AsyncWorksheetContext(ws, self)

    @retry_on_rate_limit_async
    async def delete_sheet(self, title: str) -> None:
        """Elimina la pestaña con el nombre dado."""
        spreadsheet = await self._spreadsheet()
        await spreadsheet.delete_worksheet(title)

    async def worksheet_or_create(
        self, title: str, rows: int = 100, cols: int = 26
    ) -> AsyncWorksheetContext:
        """Devuelve el handle de la pestaña ``title``, creándola si no existe."""
        try:
            return await self.worksheet(title)
        except WorksheetNotFoundError:
            return await self.create_sheet(title, rows, cols)

    @retry_on_rate_limit_async
    async def list_worksheets(self) -> list[dict[str, Any]]:
        """Lista las pestañas del documento: ``{'sheetId', 'title', 'index', ...}``."""
        spreadsheet = await self._spreadsheet()
        meta = await spreadsheet.get_metadata(None, "sheets.properties(sheetId,title,index,hidden)")
        return [sheet["properties"] for sheet in meta.get("sheets", [])]

    # ------------------------------------------------------------------
    # Documento (Drive) y propiedades
    # ------------------------------------------------------------------

    @retry_on_rate_limit_async
    async def create_spreadsheet(self, title: str, folder_id: str | None = None) -> Any:
        """Crea un nuevo documento de Google Sheets."""
        return await self._client.create(title, folder_id)

    @retry_on_rate_limit_async
    async def delete_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento por su ID."""
        await self._client.del_spreadsheet(file_id)

    @retry_on_rate_limit_async
    async def copy_spreadsheet(
        self,
        file_id: str,
        title: str | None = None,
        copy_permissions: bool = False,
        folder_id: str | None = None,
    ) -> Any:
        """Crea una copia de un documento existente."""
        return await self._client.copy(file_id, title, copy_permissions, folder_id)

    @retry_on_rate_limit_async
    async def list_spreadsheets(
        self, title: str | None = None, folder_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Lista los documentos accesibles."""
        return await self._client.list_spreadsheet_files(title, folder_id)

    @retry_on_rate_limit_async
    async def share(
        self,
        email_address: str,
        perm_type: str = "user",
        role: str = "reader",
        notify: bool = True,
        email_message: str | None = None,
        with_link: bool = False,
    ) -> Any:
        """Comparte el documento."""
        spreadsheet = await self._spreadsheet()
        return await spreadsheet.share(
            email_address, perm_type, role, notify, email_message, with_link
        )

    @retry_on_rate_limit_async
    async def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        spreadsheet = await self._spreadsheet()
        return await spreadsheet.list_permissions()

    @retry_on_rate_limit_async
    async def export(self, export_format: ExportFormat = ExportFormat.PDF) -> bytes:
        """Exporta el documento y devuelve los bytes."""
        spreadsheet = await self._spreadsheet()
        return await spreadsheet.export(export_format.value)

    @retry_on_rate_limit_async
    async def update_title(self, title: str) -> None:
        """Renombra el documento."""
        await self._update_properties({"title": title}, "title")

    @retry_on_rate_limit_async
    async def update_locale(self, locale: str) -> None:
        """Cambia el locale del documento."""
        await self._update_properties({"locale": locale}, "locale")

    @retry_on_rate_limit_async
    async def update_timezone(self, timezone: str) -> None:
        """Cambia la zona horaria del documento."""
        await self._update_properties({"timeZone": timezone}, "timeZone")

    async def _update_properties(self, properties: dict[str, Any], fields: str) -> None:
        spreadsheet = await self._spreadsheet()
        await spreadsheet.batch_update(
            {
                "requests": [
                    {"updateSpreadsheetProperties": {"properties": properties, "fields": fields}}
                ]
            }
        )


class AsyncWorksheetContext:
    """Handle async inmutable a una pestaña concreta."""

    def __init__(self, worksheet: AsyncWorksheetPort, manager: AsyncSheetManager) -> None:
        """Recibe la hoja (puerto async) y el gestor que provee la configuración."""
        self._ws = worksheet
        self._m = manager
        self.max_retries = manager.max_retries
        self.retry_backoff = manager.retry_backoff
        self._rate_limiter = manager._rate_limiter

    @property
    def worksheet(self) -> AsyncWorksheetPort:
        """Puerto de hoja subyacente (acceso directo)."""
        return self._ws

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        return self._ws.title

    # ------------------------------------------------------------------
    # Lectura / escritura
    # ------------------------------------------------------------------

    @retry_on_rate_limit_async
    async def read(
        self,
        skiprows: int = 0,
        output_format: str = "list",
        numericise: bool = False,
        render: str | None = None,
    ) -> Any:
        """Lee la hoja como ``list`` o ``dict`` (no hay salida pandas en la API async)."""
        values = await self._ws.get_all_values(_resolve_render(render))
        rows = values[skiprows:]
        if output_format == "dict":
            records = self._as_dicts(rows)
            return numericise_records(records) if numericise else records
        if output_format == "pandas":
            raise GSpreadManagerError(
                "La API async no tiene salida pandas; usá read() y construí el DataFrame, "
                "o la API síncrona."
            )
        return numericise_all(rows) if numericise else rows

    @staticmethod
    def _as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
        if not rows:
            return []
        header = rows[0]
        return [dict(zip(header, row)) for row in rows[1:]]

    async def append(self, data: list[list[Any]]) -> Any:
        """Añade filas al final (con chunking automático por ``batch_cell_limit``)."""
        chunks = split_rows(data, self._m.batch_cell_limit)
        if len(chunks) == 1:
            return await self._append_chunk(chunks[0])
        return [await self._append_chunk(chunk) for chunk in chunks]

    @retry_on_rate_limit_async
    async def _append_chunk(self, data: list[list[Any]]) -> Any:
        return await self._ws.append_rows(data, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit_async
    async def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (índices 1-based)."""
        await self._ws.update_cell(row, col, value)

    @retry_on_rate_limit_async
    async def update_row(self, row: int, data: list[Any], start_column: int | None = None) -> None:
        """Actualiza una fila celda por celda desde ``start_column`` (o la primera)."""
        for index, value in enumerate(data, start=(start_column or 1)):
            await self._ws.update_cell(row, index, value)

    async def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str = DEFAULT_VALUE_INPUT_OPTION
    ) -> None:
        """Actualiza varios rangos (con chunking automático)."""
        for chunk in split_range_data(range_data, self._m.batch_cell_limit):
            await self._batch_update_chunk(chunk, value_input_option)

    @retry_on_rate_limit_async
    async def _batch_update_chunk(
        self, range_data: list[dict[str, Any]], value_input_option: str
    ) -> None:
        await self._ws.batch_update(range_data, value_input_option)

    @retry_on_rate_limit_async
    async def clear(self, ranges: str | list[str] | None = None) -> None:
        """Limpia uno o más rangos, o toda la hoja si ``ranges`` es None."""
        if ranges is None:
            await self._ws.clear()
            return
        targets = [ranges] if isinstance(ranges, str) else ranges
        await self._ws.batch_clear(targets)

    @retry_on_rate_limit_async
    async def find(self, query: str, case_sensitive: bool = True) -> Any:
        """Busca la primera celda cuyo valor coincide; None si no hay."""
        return await self._ws.find(query, case_sensitive)

    @retry_on_rate_limit_async
    async def find_replace(
        self,
        find: str,
        replacement: str,
        *,
        match_case: bool = False,
        match_entire_cell: bool = False,
        search_by_regex: bool = False,
        include_formulas: bool = False,
    ) -> dict[str, Any]:
        """Reemplaza ocurrencias en esta pestaña (``findReplace``); devuelve el resumen."""
        request = {
            "findReplace": {
                "find": find,
                "replacement": replacement,
                "sheetId": self._ws.id,
                "matchCase": match_case,
                "matchEntireCell": match_entire_cell,
                "searchByRegex": search_by_regex,
                "includeFormulas": include_formulas,
            }
        }
        result = await self._ws.spreadsheet.batch_update({"requests": [request]})
        if isinstance(result, dict):
            replies = result.get("replies") or []
            if replies and isinstance(replies[0], dict):
                reply: dict[str, Any] = replies[0].get("findReplace", {})
                return reply
        return {}

    @retry_on_rate_limit_async
    async def copy_to(self, destination_key: str) -> Any:
        """Copia esta pestaña a otro documento (por su key de Drive)."""
        return await self._ws.copy_to(destination_key)

    @retry_on_rate_limit_async
    async def import_csv(self, source: Any, *, clear: bool = True, delimiter: str = ",") -> Any:
        """Vuelca un CSV (ruta o file-like) en la hoja desde A1."""
        if hasattr(source, "read"):
            text = source.read()
        else:
            from pathlib import Path  # noqa: PLC0415

            text = Path(source).read_text(encoding="utf-8")
        rows = rows_from_csv(text, delimiter)
        if clear:
            await self._ws.clear()
        return await self._ws.update(rows, "RAW")

    # ------------------------------------------------------------------
    # Streaming (hojas grandes)
    # ------------------------------------------------------------------

    async def iter_rows(
        self, page_size: int = 1000, skiprows: int = 0
    ) -> AsyncIterator[list[str]]:
        """Itera las filas de a páginas (lectura perezosa, una petición por página)."""
        if page_size < 1:
            raise GSpreadManagerError(f"page_size inválido: {page_size} (debe ser >= 1).")
        start = skiprows + 1
        while True:
            rows = await self._read_page(start, start + page_size - 1)
            for row in rows:
                yield row
            if len(rows) < page_size:
                return
            start += page_size

    async def iter_records(self, page_size: int = 1000) -> AsyncIterator[dict[str, str]]:
        """Itera las filas como dicts ``{columna: valor}`` (encabezado en la fila 1)."""
        header = await self._header_row()
        if header is None:
            return
        async for row in self.iter_rows(page_size, skiprows=1):
            padded = row + [""] * (len(header) - len(row))
            yield dict(zip(header, padded))

    async def iter_as(self, model: type, page_size: int = 1000) -> AsyncIterator[Any]:
        """Itera las filas como instancias de ``model`` (dataclass o Pydantic)."""
        if page_size < 1:
            raise GSpreadManagerError(f"page_size inválido: {page_size} (debe ser >= 1).")
        header = await self._header_row()
        if header is None:
            return
        start = 2
        while True:
            rows = await self._read_page(start, start + page_size - 1)
            for item in self._m._rows.to_models(model, header, rows):
                yield item
            if len(rows) < page_size:
                return
            start += page_size

    async def _header_row(self) -> list[str] | None:
        rows = await self._read_page(1, 1)
        return rows[0] if rows else None

    @retry_on_rate_limit_async
    async def _read_page(self, start: int, end: int) -> list[list[str]]:
        data = await self._ws.spreadsheet.values_get(f"{self._ws.title}!{start}:{end}")
        rows: list[list[str]] = data.get("values", []) if isinstance(data, dict) else []
        return rows

    # ------------------------------------------------------------------
    # La hoja como tabla
    # ------------------------------------------------------------------

    @retry_on_rate_limit_async
    async def upsert(
        self, rows: list[dict[str, Any]] | list[list[Any]], key: str
    ) -> dict[str, int]:
        """Actualiza por la columna clave ``key`` y agrega las filas nuevas."""
        header, values = require_header(await self._ws.get_all_values())
        updates, appends, updated_rows = plan_upsert(header, values, rows, key)
        for chunk in split_range_data(updates, self._m.batch_cell_limit):
            if chunk:
                await self._ws.batch_update(chunk, DEFAULT_VALUE_INPUT_OPTION)
        for rows_chunk in split_rows(appends, self._m.batch_cell_limit):
            if rows_chunk:
                await self._ws.append_rows(rows_chunk, DEFAULT_VALUE_INPUT_OPTION)
        return {"updated": updated_rows, "appended": len(appends)}

    @retry_on_rate_limit_async
    async def upsert_models(self, models: list[Any], key: str) -> dict[str, int]:
        """Upsert de modelos tipados (dataclasses o Pydantic) por la columna clave."""
        header, rows = self._m._rows.to_rows(models)
        records = [dict(zip(header, row)) for row in rows]
        sheet_header, values = require_header(await self._ws.get_all_values())
        updates, appends, updated_rows = plan_upsert(sheet_header, values, records, key)
        for chunk in split_range_data(updates, self._m.batch_cell_limit):
            if chunk:
                await self._ws.batch_update(chunk, DEFAULT_VALUE_INPUT_OPTION)
        for rows_chunk in split_rows(appends, self._m.batch_cell_limit):
            if rows_chunk:
                await self._ws.append_rows(rows_chunk, DEFAULT_VALUE_INPUT_OPTION)
        return {"updated": updated_rows, "appended": len(appends)}

    @retry_on_rate_limit_async
    async def update_where(self, where: Where, updates: dict[str, Any]) -> int:
        """Aplica ``updates`` a las filas que cumplen ``where``; devuelve cuántas."""
        header, values = require_header(await self._ws.get_all_values())
        range_updates, count = plan_update_where(header, values, where, updates)
        for chunk in split_range_data(range_updates, self._m.batch_cell_limit):
            if chunk:
                await self._ws.batch_update(chunk, DEFAULT_VALUE_INPUT_OPTION)
        return count

    @retry_on_rate_limit_async
    async def delete_where(self, where: Where) -> int:
        """Elimina las filas que cumplen ``where``; devuelve cuántas se borraron."""
        header, values = require_header(await self._ws.get_all_values())
        requests, count = plan_delete_requests(header, values, where, self._ws.id)
        if requests:
            await self._ws.spreadsheet.batch_update({"requests": requests})
        return count

    # ------------------------------------------------------------------
    # Modelos tipados
    # ------------------------------------------------------------------

    @retry_on_rate_limit_async
    async def read_as(self, model: type, skiprows: int = 0) -> list[Any]:
        """Lee la hoja como instancias de ``model`` (dataclass o Pydantic)."""
        values = (await self._ws.get_all_values())[skiprows:]
        if not values:
            return []
        return self._m._rows.to_models(model, values[0], values[1:])

    @retry_on_rate_limit_async
    async def append_models(self, models: list[Any]) -> Any:
        """Añade los modelos como filas al final (sin encabezado)."""
        if not models:
            return None
        _, rows = self._m._rows.to_rows(models)
        return await self._ws.append_rows(rows, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit_async
    async def write_models(
        self, models: list[Any], include_header: bool = True, clear: bool = True
    ) -> Any:
        """Escribe los modelos desde A1 (encabezado opcional), limpiando antes si ``clear``."""
        header, rows = self._m._rows.to_rows(models)
        values = ([header] if include_header and header else []) + rows
        if clear:
            await self._ws.clear()
        return await self._ws.update(values, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit_async
    async def ensure_schema(
        self, model: type, *, create: bool = True, strict: bool = False
    ) -> dict[str, Any]:
        """Valida (o crea) el encabezado de la hoja contra el esquema de ``model``."""
        expected = self._m._rows.codec_for(model).header(model)
        values = await self._ws.get_all_values()
        header = values[0] if values else []
        if not any(cell != "" for cell in header):
            if not create:
                raise SchemaError(
                    "La hoja no tiene encabezado y create=False.", missing_columns=expected
                )
            await self._ws.update([expected], "RAW")
            return {"created": True, "missing": [], "extra": []}
        missing, extra = schema_drift(expected, header)
        if missing:
            raise SchemaError(
                f"El encabezado no cubre el modelo: faltan {missing} (sobran: {extra}).",
                missing_columns=missing,
                extra_columns=extra,
            )
        if strict and extra:
            raise SchemaError(
                f"Columnas no declaradas en el modelo: {extra} (strict=True).",
                extra_columns=extra,
            )
        return {"created": False, "missing": missing, "extra": extra}
