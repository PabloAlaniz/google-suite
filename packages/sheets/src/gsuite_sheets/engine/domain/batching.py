"""Particionado de escrituras grandes (lógica pura).

La Sheets API limita el tamaño del payload por petición; estos helpers parten filas o
listas de rangos en chunks que no superan un máximo de celdas, sin partir nunca una fila
ni un rango individual. Quién itera los chunks (y aplica retry/rate limit por chunk) es
la capa de arriba.
"""

from __future__ import annotations

from typing import Any

# Máximo de celdas por petición de escritura (conservador respecto del límite de payload
# de ~2 MB de la API; ~50k celdas de texto corto rondan 1 MB).
DEFAULT_MAX_CELLS_PER_REQUEST = 50_000


def _row_cells(rows: list[list[Any]]) -> int:
    return sum(len(row) for row in rows)


def split_rows(rows: list[list[Any]], max_cells: int | None) -> list[list[list[Any]]]:
    """Parte ``rows`` en chunks consecutivos de a lo sumo ``max_cells`` celdas.

    Una fila nunca se parte (un chunk puede exceder ``max_cells`` si una sola fila lo
    supera). Con ``max_cells=None`` no se parte nada.
    """
    if max_cells is None or _row_cells(rows) <= max_cells:
        return [rows]
    chunks: list[list[list[Any]]] = []
    current: list[list[Any]] = []
    count = 0
    for row in rows:
        size = max(1, len(row))
        if current and count + size > max_cells:
            chunks.append(current)
            current, count = [], 0
        current.append(row)
        count += size
    if current:
        chunks.append(current)
    return chunks


def split_range_data(
    range_data: list[dict[str, Any]], max_cells: int | None
) -> list[list[dict[str, Any]]]:
    """Parte la lista de rangos de un ``values:batchUpdate`` por total de celdas.

    Un item (rango) nunca se parte; con ``max_cells=None`` no se parte nada.
    """
    if max_cells is None:
        return [range_data]
    sizes = [_row_cells(item.get("values", [])) for item in range_data]
    if sum(sizes) <= max_cells:
        return [range_data]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    count = 0
    for item, item_size in zip(range_data, sizes):
        size = max(1, item_size)
        if current and count + size > max_cells:
            chunks.append(current)
            current, count = [], 0
        current.append(item)
        count += size
    if current:
        chunks.append(current)
    return chunks
