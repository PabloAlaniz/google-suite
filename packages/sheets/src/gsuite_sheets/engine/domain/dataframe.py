"""Transformaciones puras de tabla (encabezado + filas) para la lectura de DataFrames.

Operan sobre listas, sin depender de pandas ni polars, de modo que el "limpiado" de filas
y columnas vacías es independiente del backend de DataFrame elegido.
"""

from __future__ import annotations

from typing import Any


def _is_empty(value: Any) -> bool:
    """True si la celda se considera vacía (``None`` o cadena vacía)."""
    return value is None or value == ""


def _column(rows: list[list[Any]], idx: int) -> list[Any]:
    """Devuelve los valores de la columna ``idx`` (``None`` si la fila no llega)."""
    return [row[idx] if idx < len(row) else None for row in rows]


def prune_empty(
    header: list[str],
    rows: list[list[Any]],
    *,
    drop_empty_rows: bool = False,
    drop_empty_cols: bool = False,
) -> tuple[list[str], list[list[Any]]]:
    """Quita filas y/o columnas totalmente vacías (``None`` o cadena vacía).

    Al descartar una columna se quita también su posición en el encabezado. No muta los
    argumentos: devuelve un nuevo ``(header, rows)``.
    """
    if drop_empty_rows:
        rows = [row for row in rows if not all(_is_empty(cell) for cell in row)]
    if drop_empty_cols and header:
        keep = [idx for idx in range(len(header)) if not all(map(_is_empty, _column(rows, idx)))]
        header = [header[idx] for idx in keep]
        rows = [[row[idx] if idx < len(row) else None for idx in keep] for row in rows]
    return header, rows
