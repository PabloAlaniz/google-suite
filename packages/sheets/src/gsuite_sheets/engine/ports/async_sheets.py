"""Puertos async de Google Sheets: espejo de ``ports.sheets`` con métodos ``async``.

Mismas firmas y semántica que ``WorksheetPort``/``SpreadsheetPort``/``ClientPort``, pero
con corrutinas: los implementa el cliente nativo async (httpx). Las propiedades de
identidad (``id``, ``title``, ``spreadsheet``, ``sheet1``) siguen siendo síncronas: no
hacen IO en las implementaciones (la metadata se carga al abrir el documento).
"""

from __future__ import annotations

from typing import Any, Protocol


class AsyncWorksheetPort(Protocol):
    """Operaciones async sobre una hoja (pestaña)."""

    @property
    def id(self) -> int:
        """Id numérico de la hoja (para GridRange)."""
        ...

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        ...

    @property
    def spreadsheet(self) -> AsyncSpreadsheetPort:
        """Documento al que pertenece la hoja."""
        ...

    async def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (índices 1-based)."""
        ...

    async def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Devuelve todas las filas como lista de listas (render opcional)."""
        ...

    async def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas al final."""
        ...

    async def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str
    ) -> None:
        """Actualiza varios rangos en una sola petición."""
        ...

    async def col_values(self, col: int) -> list[Any]:
        """Valores de una columna (1-based)."""
        ...

    async def range(self, name: str) -> list[Any]:
        """Celdas de un rango A1 (lista de ``Cell``)."""
        ...

    async def row_values(self, row: int) -> list[Any]:
        """Valores de una fila (1-based)."""
        ...

    async def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Aplica un formato (ya serializado) a uno o más rangos."""
        ...

    async def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Congela filas y/o columnas."""
        ...

    async def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Combina las celdas de un rango."""
        ...

    async def clear(self) -> None:
        """Limpia toda la hoja."""
        ...

    async def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos."""
        ...

    async def find(self, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda cuyo valor coincide; None si no hay."""
        ...

    async def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Escribe ``values`` desde A1, o desde ``range_name`` (ancla) si se indica."""
        ...

    async def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copia esta hoja a otro documento (``sheets.copyTo``)."""
        ...


class AsyncSpreadsheetPort(Protocol):
    """Operaciones async sobre un documento (spreadsheet)."""

    @property
    def sheet1(self) -> AsyncWorksheetPort:
        """Primera hoja del documento."""
        ...

    def worksheet(self, name: str) -> AsyncWorksheetPort:
        """Hoja por nombre (lookup local sobre la metadata ya cargada)."""
        ...

    async def add_worksheet(
        self, title: str, rows: int, cols: int, index: int | None
    ) -> AsyncWorksheetPort:
        """Crea una nueva hoja y la devuelve."""
        ...

    async def delete_worksheet(self, title: str) -> None:
        """Elimina la hoja con el nombre dado."""
        ...

    async def values_get(self, a1_range: str) -> Any:
        """Lee un rango A1 (``spreadsheets.values.get``)."""
        ...

    async def values_append(
        self, a1_range: str, params: dict[str, Any], body: dict[str, Any]
    ) -> Any:
        """Añade valores a un rango (``spreadsheets.values.append``)."""
        ...

    async def batch_update(self, body: dict[str, Any]) -> Any:
        """Envía una petición ``spreadsheets.batchUpdate``."""
        ...

    async def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """Lee metadata del documento (``spreadsheets.get``) filtrando por ranges/fields."""
        ...

    async def export(self, mime_type: str) -> bytes:
        """Exporta el documento al ``mime_type`` dado y devuelve los bytes."""
        ...

    async def share(
        self,
        email_address: str,
        perm_type: str,
        role: str,
        notify: bool,
        email_message: str | None,
        with_link: bool,
    ) -> Any:
        """Comparte el documento."""
        ...

    async def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        ...

    async def remove_permissions(self, value: str, role: str) -> list[str]:
        """Quita permisos; devuelve los IDs eliminados."""
        ...


class AsyncClientPort(Protocol):
    """Cliente async: abre documentos y opera a nivel Drive."""

    async def open(self, doc_name: str) -> AsyncSpreadsheetPort:
        """Abre un documento por nombre."""
        ...

    async def open_by_key(self, key: str) -> AsyncSpreadsheetPort:
        """Abre un documento por su key (id de Drive)."""
        ...

    async def create(self, title: str, folder_id: str | None) -> Any:
        """Crea un nuevo documento."""
        ...

    async def del_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento por su ID."""
        ...

    async def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> Any:
        """Copia un documento."""
        ...

    async def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista documentos accesibles."""
        ...
