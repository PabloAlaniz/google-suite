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

from typing import Any

from .application.data_service import DataService
from .application.dataframe_service import DataframeService
from .application.document_service import DocumentService
from .application.formatting_service import FormattingService
from .application.metadata_service import MetadataService
from .application.sharing_service import SharingService
from .application.validation_service import ValidationService
from .application.worksheet_service import WorksheetService
from .config import DEFAULT_VALUE_INPUT_OPTION
from .domain.errors import GSpreadManagerError
from .domain.export import ExportFormat
from .domain.numericise import numericise_all, numericise_records
from .domain.values import CellFormat, Color, SpreadsheetId
from .infrastructure.auth import build_auth_strategy
from .infrastructure.dataframe_backend import build_dataframe_adapter
from .infrastructure.gspread_client import GspreadClientAdapter
from .infrastructure.request_builders import grid_range
from .ports.sheets import WorksheetPort
from .retry import retry_on_rate_limit


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
        dataframe_backend: str = "pandas",
    ) -> None:
        """Configura la autenticación y los servicios de aplicación.

        Indicá ``doc_name`` (abrir por nombre) o ``key`` (abrir por id de Drive). Para abrir
        por URL usá el classmethod :meth:`open_by_url`. ``dataframe_backend`` elige el motor de
        DataFrame ('pandas' o 'polars') para ``read_dataframe`` / ``write_dataframe``.
        """
        if doc_name is None and key is None:
            raise GSpreadManagerError("Indicá 'doc_name' o 'key' al crear SheetManager.")
        self.doc_name = doc_name
        self._key = key
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        auth = build_auth_strategy(
            credentials=credentials,
            service_account_info=service_account_info,
            json_google_file=json_google_file,
            client=client,
            use_adc=use_adc,
        )
        self._client = GspreadClientAdapter(auth)
        self._data = DataService()
        self._formatting = FormattingService()
        self._validation = ValidationService()
        self._worksheet = WorksheetService()
        self._document = DocumentService()
        self._sharing = SharingService()
        self._metadata = MetadataService()
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

    def _spreadsheet(self, doc_name: str | None = None) -> Any:
        """Abre el documento: por ``doc_name`` explícito, o por la key/nombre del gestor."""
        name = doc_name if doc_name is not None else self.doc_name
        if name is not None:
            return self._client.open(name)
        assert self._key is not None  # garantizado por __init__  # noqa: S101
        return self._client.open_by_key(self._key)

    @retry_on_rate_limit
    def worksheet(self, tab_name: str | None = None) -> WorksheetContext:
        """Devuelve un handle inmutable a una pestaña (la primera si ``tab_name`` es None)."""
        spreadsheet = self._spreadsheet()
        ws = spreadsheet.worksheet(tab_name) if tab_name else spreadsheet.sheet1
        return WorksheetContext(ws, self)

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
        # Para que el decorador de reintentos lea la configuración de esta instancia.
        self.max_retries = manager.max_retries
        self.retry_backoff = manager.retry_backoff

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
    def read(self, skiprows: int = 0, output_format: str = "list", numericise: bool = False) -> Any:
        """Lee la hoja como ``list``, ``dict`` o ``pandas`` (según ``output_format``).

        Si ``numericise`` es True, convierte los valores a int/float cuando corresponde
        (no aplica al formato ``pandas``, que infiere tipos por su cuenta).
        """
        rows = self._m._data.read_values(self._ws, skiprows)
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

    @retry_on_rate_limit
    def append(self, data: list[list[Any]]) -> Any:
        """Añade filas al final de la hoja."""
        return self._m._data.append(self._ws, data, DEFAULT_VALUE_INPUT_OPTION)

    @retry_on_rate_limit
    def insert(self, data: list[list[Any]], fila: int | None = None) -> Any:
        """Inserta ``data`` en ``fila`` (o al final), validando lista de listas homogénea."""
        return self._m._data.insert(self._ws, self._ws.title, data, fila)

    @retry_on_rate_limit
    def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str = DEFAULT_VALUE_INPUT_OPTION
    ) -> None:
        """Actualiza varios rangos en una sola petición."""
        self._m._data.batch_update(self._ws, range_data, value_input_option)

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
