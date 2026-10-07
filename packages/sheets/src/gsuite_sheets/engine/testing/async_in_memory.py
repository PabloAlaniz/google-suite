"""Backend en memoria async: adapta el fake síncrono a los puertos async.

``AsyncInMemoryBackend`` reutiliza todo el ``InMemoryBackend`` (grillas, requests,
permisos) envolviendo sus objetos con adaptadores que exponen la superficie async. Así
los usuarios testean ``AsyncSheetManager`` sin red ni event-loop trickery:

    backend = AsyncInMemoryBackend()
    backend.add_spreadsheet("Doc", {"Hoja1": [["a"]]})
    mgr = backend.manager("Doc")
    datos = await (await mgr.worksheet("Hoja1")).read()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gspreadmanager.ports.async_sheets import AsyncSpreadsheetPort, AsyncWorksheetPort
from gspreadmanager.ports.sheets import SpreadsheetPort, WorksheetPort

from .in_memory import InMemoryBackend, InMemoryClient

if TYPE_CHECKING:
    from gspreadmanager.async_facade import AsyncSheetManager


class AsyncWorksheetAdapter:
    """``AsyncWorksheetPort`` que delega en un ``WorksheetPort`` síncrono (in-memory)."""

    def __init__(self, inner: WorksheetPort) -> None:
        """Envuelve la hoja síncrona."""
        self._inner = inner

    @property
    def id(self) -> int:
        """Id numérico de la hoja."""
        return self._inner.id

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        return self._inner.title

    @property
    def spreadsheet(self) -> AsyncSpreadsheetPort:
        """Documento (envuelto)."""
        return AsyncSpreadsheetAdapter(self._inner.spreadsheet)

    async def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda."""
        self._inner.update_cell(row, col, value)

    async def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Devuelve todas las filas."""
        return self._inner.get_all_values(value_render_option)

    async def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas al final."""
        return self._inner.append_rows(data, value_input_option)

    async def batch_update(
        self, range_data: list[dict[str, Any]], value_input_option: str
    ) -> None:
        """Actualiza varios rangos."""
        self._inner.batch_update(range_data, value_input_option)

    async def col_values(self, col: int) -> list[Any]:
        """Valores de una columna."""
        return self._inner.col_values(col)

    async def range(self, name: str) -> list[Any]:
        """Celdas de un rango A1."""
        return self._inner.range(name)

    async def row_values(self, row: int) -> list[Any]:
        """Valores de una fila."""
        return self._inner.row_values(row)

    async def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Aplica un formato (registrado por el fake)."""
        return self._inner.format(ranges, cell_format)

    async def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Congela filas/columnas."""
        return self._inner.freeze(rows, cols)

    async def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Combina celdas."""
        return self._inner.merge_cells(range_name, merge_type)

    async def clear(self) -> None:
        """Limpia toda la hoja."""
        self._inner.clear()

    async def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos."""
        self._inner.batch_clear(ranges)

    async def find(self, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda coincidente."""
        return self._inner.find(query, case_sensitive)

    async def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Escribe ``values`` desde A1 o desde ``range_name``."""
        return self._inner.update(values, value_input_option, range_name)

    async def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copia la hoja a otro documento del backend."""
        return self._inner.copy_to(destination_spreadsheet_id)


class AsyncSpreadsheetAdapter:
    """``AsyncSpreadsheetPort`` que delega en un ``SpreadsheetPort`` síncrono (in-memory)."""

    def __init__(self, inner: SpreadsheetPort) -> None:
        """Envuelve el documento síncrono."""
        self._inner = inner

    @property
    def sheet1(self) -> AsyncWorksheetPort:
        """Primera hoja del documento."""
        return AsyncWorksheetAdapter(self._inner.sheet1)

    def worksheet(self, name: str) -> AsyncWorksheetPort:
        """Hoja por nombre."""
        return AsyncWorksheetAdapter(self._inner.worksheet(name))

    async def add_worksheet(
        self, title: str, rows: int, cols: int, index: int | None
    ) -> AsyncWorksheetPort:
        """Crea una nueva hoja."""
        return AsyncWorksheetAdapter(self._inner.add_worksheet(title, rows, cols, index))

    async def delete_worksheet(self, title: str) -> None:
        """Elimina una hoja."""
        self._inner.delete_worksheet(title)

    async def values_get(self, a1_range: str) -> Any:
        """Lee un rango A1."""
        return self._inner.values_get(a1_range)

    async def values_append(
        self, a1_range: str, params: dict[str, Any], body: dict[str, Any]
    ) -> Any:
        """Añade valores a un rango."""
        return self._inner.values_append(a1_range, params, body)

    async def batch_update(self, body: dict[str, Any]) -> Any:
        """Envía un ``spreadsheets.batchUpdate``."""
        return self._inner.batch_update(body)

    async def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """Lee metadata del documento."""
        return self._inner.get_metadata(ranges, fields)

    async def export(self, mime_type: str) -> bytes:
        """Exporta el documento."""
        return self._inner.export(mime_type)

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
        return self._inner.share(email_address, perm_type, role, notify, email_message, with_link)

    async def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos."""
        return self._inner.list_permissions()

    async def remove_permissions(self, value: str, role: str) -> list[str]:
        """Quita permisos."""
        return self._inner.remove_permissions(value, role)


class AsyncClientAdapter:
    """``AsyncClientPort`` que delega en el ``InMemoryClient`` síncrono."""

    def __init__(self, inner: InMemoryClient) -> None:
        """Envuelve el cliente síncrono."""
        self._inner = inner

    async def open(self, doc_name: str) -> AsyncSpreadsheetPort:
        """Abre un documento por nombre."""
        return AsyncSpreadsheetAdapter(self._inner.open(doc_name))

    async def open_by_key(self, key: str) -> AsyncSpreadsheetPort:
        """Abre un documento por su id."""
        return AsyncSpreadsheetAdapter(self._inner.open_by_key(key))

    async def create(self, title: str, folder_id: str | None) -> Any:
        """Crea un documento."""
        return self._inner.create(title, folder_id)

    async def del_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento."""
        self._inner.del_spreadsheet(file_id)

    async def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> Any:
        """Copia un documento."""
        return self._inner.copy(file_id, title, copy_permissions, folder_id)

    async def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista documentos accesibles."""
        return self._inner.list_spreadsheet_files(title, folder_id)


class AsyncInMemoryBackend:
    """Backend en memoria para ``AsyncSheetManager`` (mismo fake, superficie async).

    Compone un ``InMemoryBackend`` síncrono: ``add_spreadsheet`` y ``client`` (para
    inspeccionar grillas/requests en los tests) son los del fake; ``manager()`` devuelve
    un ``AsyncSheetManager`` cableado a los adaptadores async.
    """

    def __init__(self) -> None:
        """Crea el backend síncrono subyacente."""
        self._backend = InMemoryBackend()

    @property
    def client(self) -> InMemoryClient:
        """Cliente síncrono subyacente (inspección en tests: grillas, requests, permisos)."""
        return self._backend.client

    def add_spreadsheet(self, doc_name: str, sheets: dict[str, list[list[Any]]] | None = None) -> Any:
        """Crea un documento con hojas precargadas (``{titulo: filas}``) y lo registra."""
        return self._backend.add_spreadsheet(doc_name, sheets)

    @property
    def async_client(self) -> AsyncClientAdapter:
        """El cliente del backend, adaptado a ``AsyncClientPort``."""
        return AsyncClientAdapter(self._backend.client)

    def manager(
        self, doc_name: str | None = None, *, key: str | None = None, **kwargs: Any
    ) -> AsyncSheetManager:
        """Devuelve un ``AsyncSheetManager`` cableado al fake (sin red)."""
        from gspreadmanager.async_facade import AsyncSheetManager  # noqa: PLC0415

        return AsyncSheetManager(doc_name, key=key, sheets_client=self.async_client, **kwargs)
