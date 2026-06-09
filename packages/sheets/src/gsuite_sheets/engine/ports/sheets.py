"""Puertos de Google Sheets: cliente, documento y hoja.

Protocols con las firmas que usa la capa de aplicación, definidas por GSpreadManager (no
por gspread). Los adaptadores de infraestructura (``infrastructure.gspread_adapters``) los
implementan envolviendo gspread; un futuro cliente nativo implementaría los mismos puertos.

``value_input_option`` se expresa como ``str`` (ej. ``"USER_ENTERED"``); la conversión al
tipo concreto de gspread vive en el adaptador.
"""

from __future__ import annotations

from typing import Any, Protocol


class WorksheetPort(Protocol):
    """Operaciones sobre una hoja (pestaña)."""

    @property
    def id(self) -> int:
        """Id numérico de la hoja (para GridRange)."""
        ...

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        ...

    @property
    def spreadsheet(self) -> SpreadsheetPort:
        """Documento al que pertenece la hoja."""
        ...

    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (índices 1-based)."""
        ...

    def get_all_values(self) -> list[list[str]]:
        """Devuelve todas las filas como lista de listas."""
        ...

    def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas al final."""
        ...

    def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Actualiza varios rangos en una sola petición."""
        ...

    def col_values(self, col: int) -> list[Any]:
        """Valores de una columna (1-based)."""
        ...

    def range(self, name: str) -> list[Any]:
        """Celdas de un rango A1 (lista de ``Cell``)."""
        ...

    def row_values(self, row: int) -> list[Any]:
        """Valores de una fila (1-based)."""
        ...

    def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Aplica un formato (ya serializado) a uno o más rangos."""
        ...

    def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Congela filas y/o columnas."""
        ...

    def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Combina las celdas de un rango."""
        ...

    def clear(self) -> None:
        """Limpia toda la hoja."""
        ...

    def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos."""
        ...

    def find(self, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda cuyo valor coincide; None si no hay."""
        ...

    def update(self, values: list[list[Any]], value_input_option: str) -> Any:
        """Escribe ``values`` desde A1."""
        ...


class SpreadsheetPort(Protocol):
    """Operaciones sobre un documento (spreadsheet)."""

    @property
    def sheet1(self) -> WorksheetPort:
        """Primera hoja del documento."""
        ...

    def worksheet(self, name: str) -> WorksheetPort:
        """Hoja por nombre."""
        ...

    def add_worksheet(self, title: str, rows: int, cols: int, index: int | None) -> WorksheetPort:
        """Crea una nueva hoja y la devuelve."""
        ...

    def delete_worksheet(self, title: str) -> None:
        """Elimina la hoja con el nombre dado."""
        ...

    def values_get(self, a1_range: str) -> Any:
        """Lee un rango A1 (``spreadsheets.values.get``)."""
        ...

    def values_append(self, a1_range: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
        """Añade valores a un rango (``spreadsheets.values.append``)."""
        ...

    def batch_update(self, body: dict[str, Any]) -> Any:
        """Envía una petición ``spreadsheets.batchUpdate``."""
        ...

    def share(
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

    def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos del documento."""
        ...

    def remove_permissions(self, value: str, role: str) -> list[str]:
        """Quita permisos; devuelve los IDs eliminados."""
        ...


class ClientPort(Protocol):
    """Cliente: abre documentos y opera a nivel Drive."""

    def open(self, doc_name: str) -> SpreadsheetPort:
        """Abre un documento por nombre."""
        ...

    def open_by_key(self, key: str) -> SpreadsheetPort:
        """Abre un documento por su key (id de Drive)."""
        ...

    def create(self, title: str, folder_id: str | None) -> Any:
        """Crea un nuevo documento."""
        ...

    def del_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento por su ID."""
        ...

    def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> Any:
        """Copia un documento."""
        ...

    def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista documentos accesibles."""
        ...
