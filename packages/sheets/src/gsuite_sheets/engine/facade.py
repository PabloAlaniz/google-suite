"""API 2.0: ``SheetManager`` + ``WorksheetContext`` (inmutable, sin estado de pestaña).

``SheetManager`` es el punto de entrada: autentica, cachea el cliente/documento y expone
operaciones a nivel documento (Drive, permisos, crear/eliminar hojas). ``worksheet(name)``
devuelve un ``WorksheetContext`` atado a una pestaña concreta, sin "hoja activa" global:
dos handles son independientes y ninguna operación muta el estado de otro.

El facade opera contra los puertos (``ClientPort`` / ``SpreadsheetPort`` / ``WorksheetPort``)
y delega la orquestación en los servicios de la capa de aplicación; los detalles de gspread
viven en los adaptadores de infraestructura.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from typing import Any

from .application.data_service import DataService
from .application.dataframe_service import DataframeService
from .application.document_service import DocumentService
from .application.formatting_service import FormattingService
from .application.metadata_service import MetadataService
from .application.row_model_service import RowModelService
from .application.sharing_service import SharingService
from .application.table_service import TableService, Where
from .application.validation_service import ValidationService
from .application.visualization_service import VisualizationService
from .application.worksheet_service import WorksheetService
from .config import DEFAULT_VALUE_INPUT_OPTION
from .domain.batching import DEFAULT_MAX_CELLS_PER_REQUEST, split_range_data, split_rows
from .domain.csv_data import rows_from_csv
from .domain.errors import GSpreadManagerError, WorksheetNotFoundError
from .domain.export import ExportFormat
from .domain.numericise import numericise_all, numericise_records
from .domain.values import (
    BandingSpec,
    CellFormat,
    ChartSpec,
    Color,
    DeveloperMetadataEntry,
    SpreadsheetId,
)
from .infrastructure.auth import GSPREAD_MISSING_MESSAGE, build_auth_strategy, build_credentials
from .infrastructure.cache import CachingClient
from .infrastructure.dataframe_backend import build_dataframe_adapter
from .infrastructure.native import DEFAULT_HTTP_TIMEOUT, SheetsApiClient, build_authorized_session
from .infrastructure.rate_limit import TokenBucketRateLimiter
from .infrastructure.request_builders import grid_range
from .ports.rate_limit import RateLimiter
from .ports.sheets import ClientPort, WorksheetPort
from .retry import retry_on_rate_limit

# Render options al leer: nombre amigable -> enum de la Sheets API.
_RENDER_OPTIONS = {
    "formatted": "FORMATTED_VALUE",
    "unformatted": "UNFORMATTED_VALUE",
    "formula": "FORMULA",
}


def _resolve_render(render: str | None) -> str | None:
    """Mapea ``render`` ('formatted'/'unformatted'/'formula') al enum de la API."""
    if render is None:
        return None
    try:
        return _RENDER_OPTIONS[render]
    except KeyError:
        raise GSpreadManagerError(
            f"render inválido: {render!r}. Usá 'formatted', 'unformatted' o 'formula'."
        ) from None


def _gspread_client_adapter(auth: Any) -> ClientPort:
    """Construye el adaptador de gspread (import diferido: gspread es un extra opcional)."""
    try:
        from .infrastructure.gspread_client import GspreadClientAdapter  # noqa: PLC0415
    except ImportError as exc:
        raise GSpreadManagerError(GSPREAD_MISSING_MESSAGE) from exc
    return GspreadClientAdapter(auth)


def _resolve_backend(backend: str | None, client: Any) -> str:
    """Resuelve el backend efectivo.

    - ``None`` (default 3.0): **nativo**, salvo que se pase un ``client`` de gspread
      preautorizado (compatibilidad).
    - ``"auto"``: gspread si está instalado (o hay ``client``), si no el nativo.
    - ``"gspread"`` / ``"native"``: explícitos.
    """
    if backend is None:
        return "gspread" if client is not None else "native"
    if backend != "auto":
        return backend
    if client is not None or importlib.util.find_spec("gspread") is not None:
        return "gspread"
    return "native"


class SheetManager:
    """Gestor de un documento de Google Sheets (API 2.0, sin estado de pestaña mutable).

    Ejemplo:
        mgr = SheetManager("MiDoc", json_google_file="creds.json")
        ws = mgr.worksheet("Hoja1")
        ws.append([["Ana", "ana@example.com"]])
        ws2 = mgr.worksheet("Hoja2")  # handle independiente
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
        client: Any = None,
        service_account_info: dict[str, Any] | None = None,
        use_adc: bool = False,
        backend: str | None = None,
        http_timeout: float | None = DEFAULT_HTTP_TIMEOUT,
        dataframe_backend: str = "pandas",
        sheets_client: ClientPort | None = None,
        cache: bool = False,
        cache_ttl: float | None = None,
        cache_max_entries: int | None = None,
        rate_limit: float | None = None,
        rate_limit_burst: float | None = None,
        batch_cell_limit: int | None = DEFAULT_MAX_CELLS_PER_REQUEST,
    ) -> None:
        """Configura la autenticación y los servicios de aplicación.

        Indicá ``doc_name`` (abrir por nombre) o ``key`` (abrir por id de Drive). Para abrir
        por URL usá el classmethod :meth:`open_by_url`. ``dataframe_backend`` elige el motor de
        DataFrame ('pandas' o 'polars') para ``read_dataframe`` / ``write_dataframe``.

        ``backend`` elige el transporte. Desde la 3.0 el default es el **cliente nativo**
        (REST propio sobre google-auth; culmina el ADR 0001), salvo que se pase ``client=``
        (un cliente de gspread preautorizado). Valores: ``"native"``, ``"gspread"`` (requiere
        el extra ``pip install "GSpreadManager[gspread]"``) o ``"auto"`` (gspread si está
        instalado, si no nativo — el default de la 2.x). ``http_timeout`` (segundos, solo
        backend nativo) limita cada petición HTTP; ``None`` lo desactiva.

        ``sheets_client`` inyecta un ``ClientPort`` propio (ej. el backend en memoria de
        ``gspreadmanager.testing``), salteando la autenticación con gspread.

        ``cache=True`` activa una caché de lecturas que se invalida con cada escritura propia
        (no detecta cambios de otros procesos); usá :meth:`clear_cache` para forzar el refresco.
        ``cache_ttl`` (segundos) expira las entradas y acota la ventana de staleness;
        ``cache_max_entries`` limita el tamaño (desalojo LRU). Pasar cualquiera de los dos
        activa la caché aunque no se indique ``cache=True``.

        ``rate_limit`` (operaciones por segundo) activa un freno proactivo de cuota (token
        bucket); ``rate_limit_burst`` fija la ráfaga máxima (por defecto ``max(1, rate_limit)``).

        ``batch_cell_limit`` (celdas por petición de escritura) parte automáticamente los
        ``append``/``batch_update``/``upsert`` grandes en varias peticiones (cada chunk con
        su propio retry y permiso del rate limiter); ``None`` desactiva el chunking.
        """
        if doc_name is None and key is None:
            raise GSpreadManagerError("Indicá 'doc_name' o 'key' al crear SheetManager.")
        self.doc_name = doc_name
        self._key = key
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.batch_cell_limit = batch_cell_limit
        self._rate_limiter: RateLimiter | None = (
            TokenBucketRateLimiter(rate_limit, rate_limit_burst) if rate_limit is not None else None
        )
        backend = _resolve_backend(backend, client)
        if sheets_client is not None:
            base_client: ClientPort = sheets_client
        elif backend == "native":
            if client is not None:
                raise GSpreadManagerError(
                    "El parámetro 'client' (cliente de gspread preautorizado) no aplica "
                    "con backend='native'; usá credentials, service_account_info, "
                    "json_google_file o use_adc."
                )
            creds = build_credentials(
                credentials=credentials,
                service_account_info=service_account_info,
                json_google_file=json_google_file,
                use_adc=use_adc,
            )
            base_client = SheetsApiClient(build_authorized_session(creds, timeout=http_timeout))
        elif backend == "gspread":
            auth = build_auth_strategy(
                credentials=credentials,
                service_account_info=service_account_info,
                json_google_file=json_google_file,
                client=client,
                use_adc=use_adc,
            )
            base_client = _gspread_client_adapter(auth)
        else:
            raise GSpreadManagerError(
                f"Backend desconocido: {backend!r}. Usá 'auto', 'gspread' o 'native'."
            )
        cache_enabled = cache or cache_ttl is not None or cache_max_entries is not None
        self._cache = (
            CachingClient(base_client, ttl=cache_ttl, max_entries=cache_max_entries)
            if cache_enabled
            else None
        )
        self._client: ClientPort = self._cache or base_client
        self._data = DataService()
        self._formatting = FormattingService()
        self._validation = ValidationService()
        self._worksheet = WorksheetService()
        self._document = DocumentService()
        self._sharing = SharingService()
        self._metadata = MetadataService()
        self._rows = RowModelService()
        self._table = TableService()
        self._visualization = VisualizationService()
        self._dataframe = DataframeService(build_dataframe_adapter(dataframe_backend))

    def __enter__(self) -> SheetManager:
        """Permite usar el gestor como context manager."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Salida del context manager (las operaciones se aplican de inmediato)."""
        return

    @classmethod
    def open_by_key(
        cls, key: str, json_google_file: str | None = None, **kwargs: Any
    ) -> SheetManager:
        """Crea un gestor para el documento con ``key`` (id de Drive)."""
        return cls(key=key, json_google_file=json_google_file, **kwargs)

    @classmethod
    def open_by_url(
        cls, url: str, json_google_file: str | None = None, **kwargs: Any
    ) -> SheetManager:
        """Crea un gestor para el documento de una URL de Google Sheets."""
        return cls(
            key=SpreadsheetId.from_url(url).value, json_google_file=json_google_file, **kwargs
        )

    def clear_cache(self) -> None:
        """Invalida la caché de lecturas (no-op si se creó con ``cache=False``)."""
        if self._cache is not None:
            self._cache.clear()

    def _spreadsheet(self, doc_name: str | None = None) -> Any:
        """Abre el documento: por ``doc_name`` explícito, o por la key/nombre del gestor."""
        name = doc_name if doc_name is not None else self.doc_name
        if name is not None:
            return self._client.open(name)
        assert self._key is not None  # garantizado por __init__  # noqa: S101  # nosec B101
        return self._client.open_by_key(self._key)

    @retry_on_rate_limit
    def worksheet(self, tab_name: str | None = None) -> WorksheetContext:
        """Devuelve un handle inmutable a una pestaña (la primera si ``tab_name`` es None)."""
        spreadsheet = self._spreadsheet()
        ws = spreadsheet.worksheet(tab_name) if tab_name else spreadsheet.sheet1
        return WorksheetContext(ws, self)

    @retry_on_rate_limit
    def list_worksheets(self) -> list[dict[str, Any]]:
        """Lista las pestañas del documento: ``{'sheetId', 'title', 'index', ...}``."""
        return self._worksheet.list_worksheets(self._spreadsheet())

    def worksheet_by_index(self, index: int) -> WorksheetContext:
        """Devuelve el handle de la pestaña en la posición ``index`` (0-based)."""
        for props in self.list_worksheets():
            if props.get("index", -1) == index:
                return self.worksheet(props["title"])
        raise WorksheetNotFoundError(f"No existe la hoja con índice {index}.")

    def worksheet_by_id(self, sheet_id: int) -> WorksheetContext:
        """Devuelve el handle de la pestaña con el ``sheetId`` dado."""
        for props in self.list_worksheets():
            if props.get("sheetId") == sheet_id:
                return self.worksheet(props["title"])
        raise WorksheetNotFoundError(f"No existe la hoja con id {sheet_id}.")

    # ------------------------------------------------------------------
    # Gestión de hojas
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def create_sheet(
        self, title: str, rows: int = 100, cols: int = 26, index: int | None = None
    ) -> WorksheetContext:
        """Crea una nueva pestaña y devuelve su handle (sin cambiar ninguna 'hoja activa')."""
        spreadsheet = self._spreadsheet()
        ws = self._worksheet.create(spreadsheet, title, rows, cols, index)
        return WorksheetContext(ws, self)

    @retry_on_rate_limit
    def delete_sheet(self, title: str) -> None:
        """Elimina la pestaña con el nombre dado."""
        self._worksheet.delete(self._spreadsheet(), title)

    def worksheet_or_create(self, title: str, rows: int = 100, cols: int = 26) -> WorksheetContext:
        """Devuelve el handle de la pestaña ``title``, creándola si no existe."""
        try:
            return self.worksheet(title)
        except WorksheetNotFoundError:
            return self.create_sheet(title, rows, cols)

    # ------------------------------------------------------------------
    # Operaciones a nivel documento (Drive)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def create_spreadsheet(self, title: str, folder_id: str | None = None) -> Any:
        """Crea un nuevo documento de Google Sheets."""
        return self._document.create(self._client, title, folder_id)

    @retry_on_rate_limit
    def delete_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento por su ID."""
        self._document.delete(self._client, file_id)

    @retry_on_rate_limit
    def copy_spreadsheet(
        self,
        file_id: str,
        title: str | None = None,
        copy_permissions: bool = False,
        folder_id: str | None = None,
    ) -> Any:
        """Crea una copia de un documento existente."""
        return self._document.copy(self._client, file_id, title, copy_permissions, folder_id)

    @retry_on_rate_limit
    def list_spreadsheets(
        self, title: str | None = None, folder_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Lista los documentos accesibles (filtrando por título/carpeta si se indica)."""
        return self._document.list(self._client, title, folder_id)

    @retry_on_rate_limit
    def update_title(self, title: str) -> None:
        """Renombra el documento (``updateSpreadsheetProperties``)."""
        self._document.update_title(self._spreadsheet(), title)

    @retry_on_rate_limit
    def update_locale(self, locale: str) -> None:
        """Cambia el locale del documento (ej. ``"es_AR"``)."""
        self._document.update_locale(self._spreadsheet(), locale)

    @retry_on_rate_limit
    def update_timezone(self, timezone: str) -> None:
        """Cambia la zona horaria del documento (ej. ``"America/Argentina/Buenos_Aires"``)."""
        self._document.update_timezone(self._spreadsheet(), timezone)

    # ------------------------------------------------------------------
    # Developer metadata (clave/valor invisible para el usuario final)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def set_developer_metadata(self, key: str, value: str, visibility: str = "DOCUMENT") -> None:
        """Guarda un par clave/valor de developer metadata anclado al documento."""
        entry = DeveloperMetadataEntry(key, value, visibility)
        self._metadata.set_developer_metadata(self._spreadsheet(), entry, sheet_id=None)

    @retry_on_rate_limit
    def list_developer_metadata(self) -> list[dict[str, Any]]:
        """Lista la developer metadata del documento y de todas sus hojas."""
        return self._metadata.list_developer_metadata(self._spreadsheet())

    @retry_on_rate_limit
    def delete_developer_metadata(self, key: str) -> None:
        """Elimina toda la developer metadata con la clave dada."""
        self._metadata.delete_developer_metadata(self._spreadsheet(), key)

    # ------------------------------------------------------------------
    # Permisos / compartir
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def share(
        self,
        email_address: str,
        role: str = "reader",
        perm_type: str = "user",
        notify: bool = True,
        email_message: str | None = None,
        with_link: bool = False,
        doc_name: str | None = None,
    ) -> Any:
        """Comparte el documento (por defecto el de este gestor) con un destinatario."""
        spreadsheet = self._spreadsheet(doc_name)
        return self._sharing.share(
            spreadsheet, email_address, role, perm_type, notify, email_message, with_link
        )

    @retry_on_rate_limit
    def list_permissions(self, doc_name: str | None = None) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        return self._sharing.list_permissions(self._spreadsheet(doc_name))

    @retry_on_rate_limit
    def remove_permission(
        self, value: str, role: str = "any", doc_name: str | None = None
    ) -> list[str]:
        """Quita el permiso de un usuario/grupo/dominio; devuelve los IDs eliminados."""
        return self._sharing.remove_permission(self._spreadsheet(doc_name), value, role)

    # ------------------------------------------------------------------
    # Named ranges (a nivel documento)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def list_named_ranges(self) -> list[dict[str, Any]]:
        """Lista los named ranges del documento."""
        return self._metadata.list_named_ranges(self._spreadsheet())

    @retry_on_rate_limit
    def delete_named_range(self, named_range_id: str) -> None:
        """Elimina un named range por su id (obtenido de ``list_named_ranges``)."""
        self._metadata.delete_named_range(self._spreadsheet(), named_range_id)

    # ------------------------------------------------------------------
    # Exportación del documento
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def export(self, export_format: str = ExportFormat.PDF) -> bytes:
        """Exporta el documento en el formato dado (ver ``ExportFormat``); devuelve bytes."""
        mime_type = (
            export_format.value if isinstance(export_format, ExportFormat) else export_format
        )
        return self._spreadsheet().export(mime_type)


class WorksheetContext:
    """Handle inmutable a una pestaña concreta. Todas las operaciones actúan sobre ella.

    No tiene parámetros ``tab_name`` ni efectos colaterales sobre otros handles: se obtiene
    con ``SheetManager.worksheet(name)`` y queda atado a esa pestaña.
    """

    def __init__(self, worksheet: WorksheetPort, manager: SheetManager) -> None:
        """Recibe la hoja (puerto) y el gestor que provee los servicios."""
        self._ws = worksheet
        self._m = manager
        # Para que el decorador de reintentos/rate-limit lea la configuración de esta instancia.
        self.max_retries = manager.max_retries
        self.retry_backoff = manager.retry_backoff
        self._rate_limiter = manager._rate_limiter

    @property
    def worksheet(self) -> WorksheetPort:
        """Devuelve el puerto de hoja subyacente por si se necesita acceso directo."""
        return self._ws

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        return self._ws.title

    # ------------------------------------------------------------------
    # Lectura / escritura de datos
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (índices 1-based)."""
        self._m._data.update_cell(self._ws, row, col, value)

    @retry_on_rate_limit
    def update_row(self, row: int, data: list[Any], start_column: int | None = None) -> None:
        """Actualiza una fila celda por celda desde ``start_column`` (o la primera)."""
        self._m._data.update_row(self._ws, row, data, start_column)

    @retry_on_rate_limit
    def read(
        self,
        skiprows: int = 0,
        output_format: str = "list",
        numericise: bool = False,
        render: str | None = None,
    ) -> Any:
        """Lee la hoja como ``list``, ``dict`` o ``pandas`` (según ``output_format``).

        Si ``numericise`` es True, convierte los valores a int/float cuando corresponde
        (no aplica al formato ``pandas``, que infiere tipos por su cuenta). ``render``
        controla cómo devuelve los valores la API: ``"formatted"`` (default),
        ``"unformatted"`` (números crudos) o ``"formula"`` (la fórmula en vez del valor).
        """
        rows = self._m._data.read_values(self._ws, skiprows, _resolve_render(render))
        if output_format == "dict":
            records = self._m._data.as_dicts(rows)
            return numericise_records(records) if numericise else records
        if output_format == "pandas":
            return self._m._dataframe.from_rows(rows[0], rows[1:])
        return numericise_all(rows) if numericise else rows

    @retry_on_rate_limit
    def read_range(
        self, fila_start: int, fila_end: int, column_start: str, column_end: str
    ) -> list[dict[str, Any]]:
        """Lee un rango por índices de fila/columna; devuelve ``{'fila': nro, 'values': [...]}``."""
        a1 = f"{self._ws.title}!{column_start}{fila_start}:{column_end}{fila_end}"
        return self._m._data.read_range(self._ws.spreadsheet, a1, fila_start)

    def append(self, data: list[list[Any]]) -> Any:
        """Añade filas al final de la hoja.

        Si ``data`` supera ``batch_cell_limit`` (celdas), se parte en varios appends —
        cada chunk con su propio retry y permiso del rate limiter — y se devuelve la
        lista de respuestas.
        """
        chunks = split_rows(data, self._m.batch_cell_limit)
        if len(chunks) == 1:
            return self._append_chunk(chunks[0])
        return [self._append_chunk(chunk) for chunk in chunks]

    @retry_on_rate_limit
    def _append_chunk(self, data: list[list[Any]]) -> Any:
        return self._m._data.append(self._ws, data, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit
    def insert(self, data: list[list[Any]], fila: int | None = None) -> Any:
        """Inserta ``data`` en ``fila`` (o al final), validando lista de listas homogénea."""
        return self._m._data.insert(self._ws, self._ws.title, data, fila)

    def iter_rows(self, page_size: int = 1000, skiprows: int = 0) -> Iterator[list[str]]:
        """Itera las filas de la hoja de a páginas de ``page_size`` (lectura perezosa).

        Pensado para hojas grandes: solo materializa una página por vez. Cada página pide
        su propio permiso al rate limiter y tiene su propio retry. Las filas se devuelven
        como vienen de la API (sin padding a un ancho uniforme).
        """
        if page_size < 1:
            raise GSpreadManagerError(f"page_size inválido: {page_size} (debe ser >= 1).")
        start = skiprows + 1
        while True:
            rows = self._read_page(start, start + page_size - 1)
            yield from rows
            if len(rows) < page_size:
                return
            start += page_size

    def iter_records(self, page_size: int = 1000) -> Iterator[dict[str, str]]:
        """Itera las filas como dicts ``{columna: valor}`` (encabezado en la fila 1)."""
        header = self._header_row()
        if header is None:
            return
        for row in self.iter_rows(page_size, skiprows=1):
            padded = row + [""] * (len(header) - len(row))
            yield dict(zip(header, padded))

    def iter_as(self, model: type, page_size: int = 1000) -> Iterator[Any]:
        """Itera las filas como instancias de ``model`` (dataclass o Pydantic), de a páginas."""
        if page_size < 1:
            raise GSpreadManagerError(f"page_size inválido: {page_size} (debe ser >= 1).")
        header = self._header_row()
        if header is None:
            return
        start = 2
        while True:
            rows = self._read_page(start, start + page_size - 1)
            yield from self._m._rows.to_models(model, header, rows)
            if len(rows) < page_size:
                return
            start += page_size

    def _header_row(self) -> list[str] | None:
        rows = self._read_page(1, 1)
        return rows[0] if rows else None

    @retry_on_rate_limit
    def _read_page(self, start: int, end: int) -> list[list[str]]:
        return self._m._data.read_page(self._ws, start, end)

    @retry_on_rate_limit
    def import_csv(self, source: Any, *, clear: bool = True, delimiter: str = ",") -> Any:
        """Vuelca un CSV en la hoja desde A1 (limpiándola antes salvo ``clear=False``).

        ``source`` puede ser una ruta (``str``/``Path``) o un objeto file-like abierto en
        modo texto. Los valores se escriben en crudo (``RAW``), sin interpretación.
        """
        if hasattr(source, "read"):
            text = source.read()
        else:
            from pathlib import Path  # noqa: PLC0415

            text = Path(source).read_text(encoding="utf-8")
        return self._m._data.import_rows(self._ws, rows_from_csv(text, delimiter), clear)

    def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str = DEFAULT_VALUE_INPUT_OPTION
    ) -> None:
        """Actualiza varios rangos en una sola petición.

        Si el total supera ``batch_cell_limit`` (celdas), se parte en varias peticiones
        (un rango individual nunca se parte).
        """
        for chunk in split_range_data(range_data, self._m.batch_cell_limit):
            self._batch_update_chunk(chunk, value_input_option)

    @retry_on_rate_limit
    def _batch_update_chunk(
        self, range_data: list[dict[str, Any]], value_input_option: str
    ) -> None:
        self._m._data.batch_update(self._ws, range_data, value_input_option)

    # ------------------------------------------------------------------
    # La hoja como tabla (encabezado en la fila 1)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def upsert(self, rows: list[dict[str, Any]] | list[list[Any]], key: str) -> dict[str, int]:
        """Actualiza por la columna clave ``key`` las filas existentes y agrega las nuevas.

        ``rows``: dicts ``{columna: valor}`` (solo se actualizan las columnas presentes) o
        listas alineadas al encabezado. Devuelve ``{"updated": n, "appended": m}``.
        """
        return self._m._table.upsert(
            self._ws, rows, key, DEFAULT_VALUE_INPUT_OPTION, self._m.batch_cell_limit
        )

    @retry_on_rate_limit
    def upsert_models(self, models: list[Any], key: str) -> dict[str, int]:
        """Upsert de modelos tipados (dataclasses o Pydantic) por la columna clave ``key``."""
        header, rows = self._m._rows.to_rows(models)
        records = [dict(zip(header, row)) for row in rows]
        return self._m._table.upsert(
            self._ws, records, key, DEFAULT_VALUE_INPUT_OPTION, self._m.batch_cell_limit
        )

    @retry_on_rate_limit
    def update_where(self, where: Where, updates: dict[str, Any]) -> int:
        """Aplica ``updates`` (``{columna: valor}``) a las filas que cumplen ``where``.

        ``where``: dict de igualdades (``{"estado": "pendiente"}``) o un predicado que
        recibe la fila como dict. Devuelve la cantidad de filas afectadas.
        """
        return self._m._table.update_where(
            self._ws, where, updates, DEFAULT_VALUE_INPUT_OPTION, self._m.batch_cell_limit
        )

    @retry_on_rate_limit
    def delete_where(self, where: Where) -> int:
        """Elimina las filas que cumplen ``where``; devuelve cuántas se borraron."""
        return self._m._table.delete_where(self._ws, where)

    @retry_on_rate_limit
    def rows_where_column_equals(self, column: int, value: Any) -> list[tuple[int, list[str]]]:
        """Devuelve ``(nro_fila, fila)`` para las filas cuya columna ``column`` es ``value``."""
        return self._m._data.rows_where_column_equals(self._ws, column, value)

    @retry_on_rate_limit
    def last_row(self) -> int:
        """Devuelve el índice (1-based) de la última fila con datos; 0 si está vacía."""
        return self._m._data.last_row(self._ws)

    @retry_on_rate_limit
    def row_with_empty_in_column(self, column_letter: str) -> tuple[list[Any] | None, int | None]:
        """Encuentra la primera fila con celda vacía en una columna; ``(None, None)`` si no hay."""
        return self._m._data.row_with_empty_in_column(self._ws, column_letter)

    # ------------------------------------------------------------------
    # Formato
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def format_range(self, ranges: str | list[str], cell_format: CellFormat) -> Any:
        """Aplica un formato a uno o más rangos."""
        return self._m._formatting.apply(self._ws, ranges, cell_format)

    def format_header(self, range_name: str = "1:1", background_hex: str | None = "#D9EAD3") -> Any:
        """Atajo de formato de encabezado (negrita + color de fondo)."""
        return self.format_range(range_name, self._m._formatting.header_format(background_hex))

    def set_background(self, ranges: str | list[str], color: Color) -> Any:
        """Aplica un color de fondo a uno o más rangos."""
        return self.format_range(ranges, CellFormat(background_color=color))

    def set_text_format(
        self,
        ranges: str | list[str],
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        font_size: int | None = None,
        color: Color | None = None,
    ) -> Any:
        """Aplica formato de texto (negrita, itálica, tamaño, color)."""
        fmt = self._m._formatting.text_format(
            bold=bold, italic=italic, font_size=font_size, color=color
        )
        return self.format_range(ranges, fmt)

    def set_number_format(
        self, ranges: str | list[str], pattern: str, number_type: str = "NUMBER"
    ) -> Any:
        """Aplica un formato numérico a uno o más rangos."""
        return self.format_range(ranges, self._m._formatting.number_format(pattern, number_type))

    @retry_on_rate_limit
    def freeze(self, rows: int | None = None, cols: int | None = None) -> Any:
        """Congela ``rows`` filas y/o ``cols`` columnas."""
        return self._m._formatting.freeze(self._ws, rows, cols)

    @retry_on_rate_limit
    def merge(self, range_name: str, merge_type: str = "MERGE_ALL") -> Any:
        """Combina las celdas de un rango."""
        return self._m._formatting.merge(self._ws, range_name, merge_type)

    # ------------------------------------------------------------------
    # Validación de datos / formato condicional
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def set_data_validation(
        self,
        range_name: str,
        condition_type: str,
        values: list[Any] | None = None,
        strict: bool = True,
        show_custom_ui: bool = True,
    ) -> Any:
        """Aplica una regla de validación de datos a un rango."""
        grid = grid_range(range_name, self._ws.id)
        return self._m._validation.set_data_validation(
            self._ws, grid, condition_type, values, strict, show_custom_ui
        )

    def add_dropdown(self, range_name: str, values: list[Any], strict: bool = True) -> Any:
        """Agrega un desplegable (lista de opciones) a un rango."""
        return self.set_data_validation(range_name, "ONE_OF_LIST", values=values, strict=strict)

    def add_checkbox(self, range_name: str) -> Any:
        """Agrega casillas de verificación (checkbox) a un rango."""
        return self.set_data_validation(range_name, "BOOLEAN")

    @retry_on_rate_limit
    def add_conditional_format(
        self,
        range_name: str,
        condition_type: str,
        values: list[Any],
        cell_format: CellFormat,
        index: int = 0,
    ) -> Any:
        """Agrega una regla de formato condicional booleana a un rango."""
        grid = grid_range(range_name, self._ws.id)
        return self._m._validation.add_conditional_format(
            self._ws, grid, condition_type, values, cell_format, index
        )

    # ------------------------------------------------------------------
    # Limpieza / búsqueda
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def clear(self, ranges: str | list[str] | None = None) -> None:
        """Limpia uno o más rangos, o toda la hoja si ``ranges`` es None."""
        self._m._worksheet.clear(self._ws, ranges)

    @retry_on_rate_limit
    def find_replace(
        self,
        find: str,
        replacement: str,
        *,
        match_case: bool = False,
        match_entire_cell: bool = False,
        search_by_regex: bool = False,
        include_formulas: bool = False,
    ) -> dict[str, Any]:
        """Reemplaza ocurrencias de ``find`` por ``replacement`` en esta pestaña.

        Devuelve el resumen de la API (``occurrencesChanged``, ``valuesChanged``, ...).
        Con ``search_by_regex=True``, ``find`` es una regex (sintaxis RE2 de Google).
        """
        return self._m._worksheet.find_replace(
            self._ws,
            find,
            replacement,
            match_case=match_case,
            match_entire_cell=match_entire_cell,
            search_by_regex=search_by_regex,
            include_formulas=include_formulas,
        )

    @retry_on_rate_limit
    def copy_to(self, destination_key: str) -> Any:
        """Copia esta pestaña a otro documento (por su key de Drive).

        Devuelve las propiedades de la hoja creada (``sheetId``, ``title``, ...). El
        destino debe ser accesible con las mismas credenciales.
        """
        return self._ws.copy_to(destination_key)

    @retry_on_rate_limit
    def find(self, query: str, case_sensitive: bool = True) -> Any:
        """Busca la primera celda cuyo valor coincide con ``query``; None si no hay."""
        return self._m._worksheet.find(self._ws, query, case_sensitive)

    # ------------------------------------------------------------------
    # Filas / columnas (posiciones 1-based)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def insert_rows(self, at: int, number: int = 1, inherit_from_before: bool = False) -> None:
        """Inserta ``number`` filas en blanco antes de la fila ``at`` (1-based)."""
        self._m._worksheet.insert_dimension(
            self._ws, "ROWS", at - 1, at - 1 + number, inherit_from_before
        )

    @retry_on_rate_limit
    def insert_cols(self, at: int, number: int = 1, inherit_from_before: bool = False) -> None:
        """Inserta ``number`` columnas en blanco antes de la columna ``at`` (1-based)."""
        self._m._worksheet.insert_dimension(
            self._ws, "COLUMNS", at - 1, at - 1 + number, inherit_from_before
        )

    @retry_on_rate_limit
    def delete_rows(self, start: int, end: int | None = None) -> None:
        """Elimina las filas ``start..end`` (1-based, inclusivo); ``end=None`` borra una."""
        self._m._worksheet.delete_dimension(self._ws, "ROWS", start - 1, end or start)

    @retry_on_rate_limit
    def delete_cols(self, start: int, end: int | None = None) -> None:
        """Elimina las columnas ``start..end`` (1-based, inclusivo); ``end=None`` borra una."""
        self._m._worksheet.delete_dimension(self._ws, "COLUMNS", start - 1, end or start)

    @retry_on_rate_limit
    def add_rows(self, number: int) -> None:
        """Agrega ``number`` filas al final de la hoja."""
        self._m._worksheet.append_dimension(self._ws, "ROWS", number)

    @retry_on_rate_limit
    def add_cols(self, number: int) -> None:
        """Agrega ``number`` columnas al final de la hoja."""
        self._m._worksheet.append_dimension(self._ws, "COLUMNS", number)

    @retry_on_rate_limit
    def resize_rows(self, start: int, end: int, pixels: int) -> None:
        """Fija la altura (en píxeles) de las filas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "ROWS", start - 1, end, {"pixelSize": pixels}, "pixelSize"
        )

    @retry_on_rate_limit
    def resize_cols(self, start: int, end: int, pixels: int) -> None:
        """Fija el ancho (en píxeles) de las columnas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "COLUMNS", start - 1, end, {"pixelSize": pixels}, "pixelSize"
        )

    @retry_on_rate_limit
    def hide_rows(self, start: int, end: int | None = None) -> None:
        """Oculta las filas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "ROWS", start - 1, end or start, {"hiddenByUser": True}, "hiddenByUser"
        )

    @retry_on_rate_limit
    def unhide_rows(self, start: int, end: int | None = None) -> None:
        """Muestra las filas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "ROWS", start - 1, end or start, {"hiddenByUser": False}, "hiddenByUser"
        )

    @retry_on_rate_limit
    def hide_cols(self, start: int, end: int | None = None) -> None:
        """Oculta las columnas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "COLUMNS", start - 1, end or start, {"hiddenByUser": True}, "hiddenByUser"
        )

    @retry_on_rate_limit
    def unhide_cols(self, start: int, end: int | None = None) -> None:
        """Muestra las columnas ``start..end`` (1-based, inclusivo)."""
        self._m._worksheet.update_dimension(
            self._ws, "COLUMNS", start - 1, end or start, {"hiddenByUser": False}, "hiddenByUser"
        )

    # ------------------------------------------------------------------
    # Notas de celda
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def update_note(self, cell: str, text: str) -> None:
        """Fija la nota de una celda (ej. ``update_note("B2", "revisar")``)."""
        self._m._metadata.set_note(self._ws, grid_range(cell, self._ws.id), text)

    @retry_on_rate_limit
    def clear_note(self, cell: str) -> None:
        """Quita la nota de una celda."""
        self._m._metadata.set_note(self._ws, grid_range(cell, self._ws.id), "")

    @retry_on_rate_limit
    def get_note(self, cell: str) -> str:
        """Devuelve la nota de una celda (cadena vacía si no tiene)."""
        return self._m._metadata.get_note(self._ws, f"{self._ws.title}!{cell}")

    # ------------------------------------------------------------------
    # Named ranges / protected ranges
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def define_named_range(self, name: str, range_name: str) -> None:
        """Define un named range que apunta a un rango A1 de esta hoja."""
        self._m._metadata.define_named_range(self._ws, name, grid_range(range_name, self._ws.id))

    @retry_on_rate_limit
    def add_protected_range(
        self, range_name: str, description: str | None = None, warning_only: bool = False
    ) -> None:
        """Protege un rango A1 de esta hoja (``warning_only`` solo advierte)."""
        self._m._metadata.add_protected_range(
            self._ws, grid_range(range_name, self._ws.id), description, warning_only
        )

    @retry_on_rate_limit
    def list_protected_ranges(self) -> list[dict[str, Any]]:
        """Lista los rangos protegidos de esta hoja."""
        return self._m._metadata.list_protected_ranges(self._ws)

    @retry_on_rate_limit
    def delete_protected_range(self, protected_range_id: str) -> None:
        """Quita la protección de un rango por su id (de ``list_protected_ranges``)."""
        self._m._metadata.delete_protected_range(self._ws.spreadsheet, protected_range_id)

    # ------------------------------------------------------------------
    # Orden / filtro / merge / color de pestaña
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def sort_range(self, range_name: str, *specs: tuple[int, str]) -> None:
        """Ordena un rango por columnas. Cada spec es ``(columna_1based, 'asc'|'desc')``."""
        sort_specs = [
            {
                "dimensionIndex": col - 1,
                "sortOrder": "DESCENDING" if order.lower().startswith("desc") else "ASCENDING",
            }
            for col, order in specs
        ]
        self._m._worksheet.sort_range(self._ws, grid_range(range_name, self._ws.id), sort_specs)

    @retry_on_rate_limit
    def set_basic_filter(self, range_name: str | None = None) -> None:
        """Activa un filtro básico sobre un rango (o toda la hoja si ``range_name`` es None)."""
        grid = grid_range(range_name, self._ws.id) if range_name else None
        self._m._worksheet.set_basic_filter(self._ws, grid)

    @retry_on_rate_limit
    def clear_basic_filter(self) -> None:
        """Quita el filtro básico de la hoja."""
        self._m._worksheet.clear_basic_filter(self._ws)

    @retry_on_rate_limit
    def unmerge(self, range_name: str) -> None:
        """Deshace la combinación de celdas de un rango."""
        self._m._worksheet.unmerge(self._ws, grid_range(range_name, self._ws.id))

    @retry_on_rate_limit
    def set_tab_color(self, color: Color) -> None:
        """Fija el color de la pestaña."""
        self._m._worksheet.set_tab_color(self._ws, color)

    # ------------------------------------------------------------------
    # Charts, pivot tables, banding y developer metadata
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def add_chart(
        self,
        chart_type: str,
        domain: str,
        series: list[str],
        *,
        title: str | None = None,
        anchor_cell: str = "A1",
        legend: str = "BOTTOM_LEGEND",
    ) -> int | None:
        """Agrega un gráfico embebido y devuelve su ``chartId``.

        ``chart_type``: LINE, BAR, COLUMN, AREA, SCATTER o PIE. ``domain`` es el rango de
        etiquetas (eje X / categorías) y ``series`` los rangos de datos (PIE usa solo el
        primero). El gráfico se ancla en ``anchor_cell``.
        """
        spec = ChartSpec(chart_type, title=title, legend_position=legend)
        return self._m._visualization.add_chart(self._ws, spec, domain, series, anchor_cell)

    @retry_on_rate_limit
    def delete_chart(self, chart_id: int) -> None:
        """Elimina un gráfico embebido por su id."""
        self._m._visualization.delete_chart(self._ws, chart_id)

    @retry_on_rate_limit
    def add_pivot_table(
        self,
        source: str,
        anchor_cell: str,
        *,
        rows: list[int],
        values: list[tuple[int, str]],
        columns: list[int] | None = None,
    ) -> None:
        """Escribe una pivot table en ``anchor_cell`` a partir del rango ``source``.

        ``rows``/``columns``: offsets 0-based de columnas del rango fuente para agrupar.
        ``values``: pares ``(offset, función)`` con función SUM/COUNT/COUNTA/AVERAGE/MAX/
        MIN/MEDIAN.
        """
        self._m._visualization.add_pivot_table(
            self._ws, source, anchor_cell, rows, values, columns or []
        )

    @retry_on_rate_limit
    def set_banding(
        self,
        range_name: str,
        *,
        first_color: Color,
        second_color: Color,
        header_color: Color | None = None,
    ) -> int | None:
        """Aplica bandas de color alternadas por fila; devuelve el ``bandedRangeId``."""
        spec = BandingSpec(first_color, second_color, header_color)
        return self._m._visualization.set_banding(self._ws, spec, range_name)

    @retry_on_rate_limit
    def delete_banding(self, banded_range_id: int) -> None:
        """Quita las bandas alternadas por su id."""
        self._m._visualization.delete_banding(self._ws, banded_range_id)

    @retry_on_rate_limit
    def set_developer_metadata(self, key: str, value: str, visibility: str = "DOCUMENT") -> None:
        """Guarda un par clave/valor de developer metadata anclado a esta pestaña."""
        entry = DeveloperMetadataEntry(key, value, visibility)
        self._m._metadata.set_developer_metadata(self._ws.spreadsheet, entry, self._ws.id)

    @retry_on_rate_limit
    def clear_tab_color(self) -> None:
        """Quita el color de la pestaña."""
        self._m._worksheet.clear_tab_color(self._ws)

    # ------------------------------------------------------------------
    # Integración con pandas
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def read_dataframe(
        self,
        skiprows: int = 0,
        *,
        drop_empty_rows: bool = False,
        drop_empty_cols: bool = False,
        index_col: str | None = None,
    ) -> Any:
        """Lee la hoja como un DataFrame (backend del gestor: pandas o polars).

        ``drop_empty_rows``/``drop_empty_cols`` descartan filas/columnas totalmente vacías;
        ``index_col`` fija una columna como índice (solo pandas).
        """
        rows = self._m._data.read_values(self._ws, skiprows)
        header = rows[0] if rows else []
        return self._m._dataframe.from_rows(
            header,
            rows[1:],
            index_col=index_col,
            drop_empty_rows=drop_empty_rows,
            drop_empty_cols=drop_empty_cols,
        )

    @retry_on_rate_limit
    def write_dataframe(
        self,
        df: Any,
        include_header: bool = True,
        clear: bool = True,
        *,
        start_cell: str | None = None,
        include_index: bool = False,
    ) -> Any:
        """Escribe un DataFrame en la hoja (desde A1 o ``start_cell``), limpiándola si ``clear``.

        ``include_index`` vuelca también el índice como primera columna (solo pandas).
        """
        return self._m._dataframe.write(
            self._ws,
            df,
            include_header,
            clear,
            DEFAULT_VALUE_INPUT_OPTION,
            include_index=include_index,
            start_cell=start_cell,
        )

    # ------------------------------------------------------------------
    # Modelos de fila tipados (dataclasses)
    # ------------------------------------------------------------------

    @retry_on_rate_limit
    def ensure_schema(self, model: type, *, create: bool = True, strict: bool = False) -> dict[str, Any]:
        """Valida (o crea) el encabezado de la hoja contra el esquema de ``model``.

        Hoja vacía: escribe el encabezado del modelo (salvo ``create=False``). Columnas del
        modelo ausentes en la hoja: ``SchemaError`` con ``missing_columns``/``extra_columns``.
        Columnas extra: se reportan (y con ``strict=True``, fallan). Devuelve
        ``{"created": bool, "missing": [...], "extra": [...]}``.
        """
        return self._m._rows.ensure_schema(self._ws, model, create=create, strict=strict)

    @retry_on_rate_limit
    def read_as(self, model: type, skiprows: int = 0) -> list[Any]:
        """Lee la hoja como una lista de instancias de ``model`` (un ``@dataclass``).

        El encabezado (1ª fila tras ``skiprows``) mapea a los campos del modelo por nombre, o
        por ``field(metadata={"column": ...})``. Los valores se convierten al tipo anotado.
        """
        return self._m._rows.read(self._ws, model, skiprows)

    @retry_on_rate_limit
    def append_models(self, models: list[Any]) -> Any:
        """Añade instancias de dataclass como filas al final (sin reescribir el encabezado)."""
        return self._m._rows.append(self._ws, models, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit
    def write_models(
        self, models: list[Any], include_header: bool = True, clear: bool = True
    ) -> Any:
        """Escribe instancias de dataclass desde A1 (encabezado opcional), limpiando si ``clear``."""
        return self._m._rows.write(
            self._ws, models, include_header, clear, DEFAULT_VALUE_INPUT_OPTION
        )
