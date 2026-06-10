"""Caché de lecturas con invalidación al escribir, sobre los puertos de Sheets.

Envuelve un ``ClientPort`` y memoiza las lecturas costosas (``get_all_values``, ``values_get``,
``get_metadata``) por documento, con **TTL** y **límite de entradas (LRU)** opcionales. La
invalidación es selectiva: una escritura puntual (``update_cell``, ``batch_update`` de rangos,
``batch_clear``) solo invalida lo que se superpone con el rango escrito; las escrituras de
alcance hoja (``update``, ``append``, ``clear``, formato) invalidan esa hoja; las operaciones a
nivel documento invalidan todo. (No detecta cambios hechos por otros procesos: por eso la
caché es opt-in; el TTL acota esa ventana.)

Es transparente: implementa los mismos puertos, así que la capa de aplicación no se entera.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Callable

from gspreadmanager.domain.values import GridRange, rowcol_to_a1
from gspreadmanager.ports.sheets import ClientPort, SpreadsheetPort, WorksheetPort

logger = logging.getLogger(__name__)


def _range_title(a1_range: str) -> str | None:
    """Título de pestaña de un rango A1 calificado ('Hoja!A1:B2'), o None si no trae."""
    if "!" not in a1_range:
        return None
    return a1_range.split("!", 1)[0].strip("'")


class _Cache:
    """Memo clave -> valor por documento, con TTL, LRU e invalidación selectiva."""

    def __init__(
        self,
        ttl: float | None = None,
        max_entries: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()
        self._ttl = ttl
        self._max_entries = max_entries
        self._clock = clock

    def load(self, key: Any, loader: Callable[[], Any]) -> Any:
        """Devuelve el valor cacheado para ``key`` (si no expiró) o lo calcula y lo guarda."""
        now = self._clock()
        if key in self._store:
            value, stored_at = self._store[key]
            if self._ttl is None or now - stored_at < self._ttl:
                self._store.move_to_end(key)
                logger.debug("Caché hit: %r.", key)
                return value
            del self._store[key]
            logger.debug("Caché TTL expirado: %r.", key)
        logger.debug("Caché miss: %r.", key)
        value = loader()
        self._store[key] = (value, now)
        if self._max_entries is not None:
            while len(self._store) > self._max_entries:
                evicted, _ = self._store.popitem(last=False)
                logger.debug("Caché LRU evict: %r.", evicted)
        return value

    def clear(self) -> None:
        """Invalida todo lo cacheado (escrituras a nivel documento)."""
        if self._store:
            logger.debug("Caché invalidada (%d entradas).", len(self._store))
        self._store.clear()

    def _drop(self, predicate: Callable[[Any], bool]) -> None:
        for key in [k for k in self._store if predicate(k)]:
            del self._store[key]

    def invalidate_sheet(self, sheet_id: int, title: str) -> None:
        """Invalida lo cacheado de una hoja (y la metadata, que es a nivel documento)."""
        self._drop(lambda key: self._belongs_to_sheet(key, sheet_id, title))

    def invalidate_range(self, sheet_id: int, title: str, a1_range: str) -> None:
        """Invalida lo que se superpone con ``a1_range`` de la hoja (y la metadata)."""
        written = GridRange.from_a1(a1_range, 0)

        def affected(key: Any) -> bool:
            kind = key[0]
            if kind == "get_all_values":
                return bool(key[1] == sheet_id)
            if kind == "values_get":
                return self._cached_range_overlaps(key[1], title, written)
            return True  # metadata u otros: conservador

        self._drop(affected)

    @staticmethod
    def _belongs_to_sheet(key: Any, sheet_id: int, title: str) -> bool:
        kind = key[0]
        if kind == "get_all_values":
            return bool(key[1] == sheet_id)
        if kind == "values_get":
            cached_title = _range_title(key[1])
            return cached_title is None or cached_title == title
        return True  # metadata u otros: conservador

    @staticmethod
    def _cached_range_overlaps(cached_a1: str, title: str, written: GridRange) -> bool:
        cached_title = _range_title(cached_a1)
        if cached_title is None:
            return True  # sin pestaña: conservador
        if cached_title != title:
            return False
        try:
            cached = GridRange.from_a1(cached_a1, 0)
        except Exception:
            return True
        return cached.overlaps(written)


class CachingWorksheet:
    """``WorksheetPort`` que cachea ``get_all_values`` e invalida según el alcance escrito."""

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

    # -- escrituras (invalidan según su alcance) ---------------------------

    def update_cell(self, row: int, col: int, value: Any) -> None:
        """Actualiza una celda (invalida solo lo que se superpone con ella)."""
        self._inner.update_cell(row, col, value)
        self._cache.invalidate_range(self._inner.id, self._inner.title, rowcol_to_a1(row, col))

    def append_rows(self, data: list[list[Any]], value_input_option: str) -> Any:
        """Añade filas al final (invalida la hoja)."""
        result = self._inner.append_rows(data, value_input_option)
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)
        return result

    def batch_update(self, range_data: list[dict[str, Any]], value_input_option: str) -> None:
        """Actualiza varios rangos (invalida solo lo superpuesto con cada rango)."""
        self._inner.batch_update(range_data, value_input_option)
        for item in range_data:
            self._cache.invalidate_range(self._inner.id, self._inner.title, item["range"])

    def update(
        self, values: list[list[Any]], value_input_option: str, range_name: str | None = None
    ) -> Any:
        """Escribe ``values`` desde A1 o desde ``range_name`` (invalida la hoja)."""
        result = self._inner.update(values, value_input_option, range_name)
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)
        return result

    def format(self, ranges: str | list[str], cell_format: dict[str, Any]) -> Any:
        """Aplica un formato (puede cambiar el valor formateado: invalida la hoja)."""
        result = self._inner.format(ranges, cell_format)
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)
        return result

    def freeze(self, rows: int | None, cols: int | None) -> Any:
        """Congela filas/columnas (invalida la hoja)."""
        result = self._inner.freeze(rows, cols)
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)
        return result

    def merge_cells(self, range_name: str, merge_type: str) -> Any:
        """Combina celdas (invalida la hoja)."""
        result = self._inner.merge_cells(range_name, merge_type)
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)
        return result

    def clear(self) -> None:
        """Limpia toda la hoja (invalida la hoja)."""
        self._inner.clear()
        self._cache.invalidate_sheet(self._inner.id, self._inner.title)

    def batch_clear(self, ranges: list[str]) -> None:
        """Limpia varios rangos (invalida solo lo superpuesto con cada rango)."""
        self._inner.batch_clear(ranges)
        for a1_range in ranges:
            self._cache.invalidate_range(self._inner.id, self._inner.title, a1_range)

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

    # -- escrituras (invalidan la caché del documento) ----------------------

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
        """Envía un ``spreadsheets.batchUpdate`` (alcance desconocido: invalida todo)."""
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

    def __init__(
        self, inner: ClientPort, ttl: float | None = None, max_entries: int | None = None
    ) -> None:
        """Envuelve el cliente ``inner``; ``ttl`` (segundos) y ``max_entries`` (LRU) opcionales."""
        self._inner = inner
        self._ttl = ttl
        self._max_entries = max_entries
        self._caches: dict[str, _Cache] = {}

    def _cache_for(self, key: str) -> _Cache:
        return self._caches.setdefault(key, _Cache(self._ttl, self._max_entries))

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
