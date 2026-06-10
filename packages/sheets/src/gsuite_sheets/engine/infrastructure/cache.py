"""Caché de lecturas con invalidación al escribir, sobre los puertos de Sheets.

Envuelve un ``ClientPort`` y memoiza las lecturas costosas (``get_all_values``, ``values_get``,
``get_metadata``) por documento. Cualquier escritura —a nivel hoja o documento— limpia la caché
de ese documento, de modo que nunca se sirve un valor obsoleto respecto de nuestras propias
escrituras. (No detecta cambios hechos por otros procesos: por eso la caché es opt-in.)

Es transparente: implementa los mismos puertos, así que la capa de aplicación no se entera.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from gspreadmanager.ports.sheets import ClientPort, SpreadsheetPort, WorksheetPort

logger = logging.getLogger(__name__)


class _Cache:
    """Memo simple clave -> valor, compartido por todas las hojas de un documento."""

    def __init__(self) -> None:
        self._store: dict[Any, Any] = {}

    def load(self, key: Any, loader: Callable[[], Any]) -> Any:
        """Devuelve el valor cacheado para ``key`` o lo calcula con ``loader`` y lo guarda."""
        if key not in self._store:
            logger.debug("Caché miss: %r.", key)
            self._store[key] = loader()
        else:
            logger.debug("Caché hit: %r.", key)
        return self._store[key]

    def clear(self) -> None:
        """Invalida todo lo cacheado (se llama tras cada escritura)."""
        if self._store:
            logger.debug("Caché invalidada (%d entradas).", len(self._store))
        self._store.clear()


class CachingWorksheet:
    """``WorksheetPort`` que cachea ``get_all_values`` y limpia la caché en cada escritura."""

    def __init__(self, inner: WorksheetPort, cache: _Cache) -> None:
        """Envuelve la hoja ``inner`` compartiendo el ``cache`` del documento."""
        self._inner = inner
        self._cache = cache

    @property
    def id(self) -> int:
        """Id numérico de la hoja."""
        return self._inner.id

    @property
    def title(self) -> str:
        """Nombre de la pestaña."""
        return self._inner.title

    @property
    def spreadsheet(self) -> SpreadsheetPort:
        """Documento (envuelto), compartiendo la misma caché."""
        return CachingSpreadsheet(self._inner.spreadsheet, self._cache)

    def get_all_values(self, value_render_option: str | None = None) -> list[list[str]]:
        """Lee todas las filas (memoizado por hoja y render option)."""
        return self._cache.load(
            ("get_all_values", self._inner.id, value_render_option),
            lambda: self._inner.get_all_values(value_render_option),
        )

    # -- lecturas no memoizadas (pasan directo) ---------------------------

    def col_values(self, col: int) -> list[Any]:
        """Valores de una columna."""
        return self._inner.col_values(col)

    def row_values(self, row: int) -> list[Any]:
        """Valores de una fila."""
        return self._inner.row_values(row)

    def range(self, name: str) -> list[Any]:
        """Celdas de un rango A1."""
        return self._inner.range(name)

    def find(self, query: str, case_sensitive: bool) -> Any:
        """Busca la primera celda coincidente."""
        return self._inner.find(query, case_sensitive)

    # -- escrituras (invalidan la caché) ----------------------------------

    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda."""
        self._inner.update_cell(row, col, value)
        self._cache.clear()

    def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas al final."""
        result = self._inner.append_rows(data, value_input_option)
        self._cache.clear()
        return result

    def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Actualiza varios rangos."""
        self._inner.batch_update(range_data, value_input_option)
        self._cache.clear()

    def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Escribe ``values`` desde A1 o desde ``range_name``."""
        result = self._inner.update(values, value_input_option, range_name)
        self._cache.clear()
        return result

    def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Aplica un formato."""
        result = self._inner.format(ranges, cell_format)
        self._cache.clear()
        return result

    def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Congela filas/columnas."""
        result = self._inner.freeze(rows, cols)
        self._cache.clear()
        return result

    def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Combina celdas."""
        result = self._inner.merge_cells(range_name, merge_type)
        self._cache.clear()
        return result

    def clear(self) -> None:
        """Limpia toda la hoja."""
        self._inner.clear()
        self._cache.clear()

    def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos."""
        self._inner.batch_clear(ranges)
        self._cache.clear()

    def copy_to(self, destination_spreadsheet_id: str) -> Any:
        """Copia la hoja a otro documento.

        Nota: escribe en el documento *destino*; si ese documento está abierto con caché
        en el mismo gestor, su caché no se invalida (usá ``clear_cache()``).
        """
        return self._inner.copy_to(destination_spreadsheet_id)


class CachingSpreadsheet:
    """``SpreadsheetPort`` que cachea ``values_get``/``get_metadata`` e invalida al escribir."""

    def __init__(self, inner: SpreadsheetPort, cache: _Cache) -> None:
        """Envuelve el documento ``inner`` compartiendo el ``cache``."""
        self._inner = inner
        self._cache = cache

    @property
    def sheet1(self) -> WorksheetPort:
        """Primera hoja (envuelta)."""
        return CachingWorksheet(self._inner.sheet1, self._cache)

    def worksheet(self, name: str) -> WorksheetPort:
        """Hoja por nombre (envuelta)."""
        return CachingWorksheet(self._inner.worksheet(name), self._cache)

    def values_get(self, a1_range: str) -> Any:
        """Lee un rango A1 (memoizado por rango)."""
        return self._cache.load(("values_get", a1_range), lambda: self._inner.values_get(a1_range))

    def get_metadata(self, ranges: list[str] | None, fields: str) -> dict[str, Any]:
        """Lee metadata (memoizado por ranges/fields)."""
        key = ("get_metadata", tuple(ranges) if ranges is not None else None, fields)
        return self._cache.load(key, lambda: self._inner.get_metadata(ranges, fields))

    # -- escrituras (invalidan la caché) ----------------------------------

    def add_worksheet(self, title: str, rows: int, cols: int, index: int | None) -> WorksheetPort:
        """Crea una nueva hoja."""
        ws = self._inner.add_worksheet(title, rows, cols, index)
        self._cache.clear()
        return CachingWorksheet(ws, self._cache)

    def delete_worksheet(self, title: str) -> None:
        """Elimina una hoja."""
        self._inner.delete_worksheet(title)
        self._cache.clear()

    def values_append(self, a1_range: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
        """Añade valores a un rango."""
        result = self._inner.values_append(a1_range, params, body)
        self._cache.clear()
        return result

    def batch_update(self, body: dict[str, Any]) -> Any:
        """Envía un ``spreadsheets.batchUpdate``."""
        result = self._inner.batch_update(body)
        self._cache.clear()
        return result

    def export(self, mime_type: str) -> bytes:
        """Exporta el documento (no se cachea)."""
        return self._inner.export(mime_type)

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
        return self._inner.share(email_address, perm_type, role, notify, email_message, with_link)

    def list_permissions(self) -> list[dict[str, Any]]:
        """Lista los permisos."""
        return self._inner.list_permissions()

    def remove_permissions(self, value: str, role: str) -> list[str]:
        """Quita permisos."""
        return self._inner.remove_permissions(value, role)


class CachingClient:
    """``ClientPort`` que entrega documentos cacheados (una caché por nombre/key)."""

    def __init__(self, inner: ClientPort) -> None:
        """Envuelve el cliente ``inner``."""
        self._inner = inner
        self._caches: dict[str, _Cache] = {}

    def _cache_for(self, key: str) -> _Cache:
        return self._caches.setdefault(key, _Cache())

    def clear(self) -> None:
        """Invalida la caché de todos los documentos abiertos."""
        for cache in self._caches.values():
            cache.clear()

    def open(self, doc_name: str) -> SpreadsheetPort:
        """Abre un documento por nombre (con caché)."""
        return CachingSpreadsheet(self._inner.open(doc_name), self._cache_for(doc_name))

    def open_by_key(self, key: str) -> SpreadsheetPort:
        """Abre un documento por su key (con caché)."""
        return CachingSpreadsheet(self._inner.open_by_key(key), self._cache_for(key))

    # -- operaciones de Drive (sin caché) ---------------------------------

    def create(self, title: str, folder_id: str | None) -> Any:
        """Crea un documento."""
        return self._inner.create(title, folder_id)

    def del_spreadsheet(self, file_id: str) -> None:
        """Elimina un documento."""
        self._inner.del_spreadsheet(file_id)

    def copy(
        self, file_id: str, title: str | None, copy_permissions: bool, folder_id: str | None
    ) -> Any:
        """Copia un documento."""
        return self._inner.copy(file_id, title, copy_permissions, folder_id)

    def list_spreadsheet_files(
        self, title: str | None, folder_id: str | None
    ) -> list[dict[str, Any]]:
        """Lista documentos accesibles."""
        return self._inner.list_spreadsheet_files(title, folder_id)
