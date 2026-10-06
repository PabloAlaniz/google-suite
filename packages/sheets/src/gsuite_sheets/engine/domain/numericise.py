"""Inferencia de tipos de valores leídos (equivalente nativo de ``gspread.numericise``).

La Sheets API devuelve los valores como strings; estas funciones los convierten a ``int`` /
``float`` cuando corresponde. Conservan los strings con ceros a la izquierda (ej. códigos
postales o teléfonos) para no perder información.
"""

from __future__ import annotations

from typing import Any


def numericise(value: Any, *, empty_to_zero: bool = False, default_blank: Any = "") -> Any:
    """Convierte ``value`` a ``int``/``float`` si es posible; si no, lo deja igual.

    - ``""`` -> ``0`` si ``empty_to_zero``, o ``default_blank`` en caso contrario.
    - Strings con ceros a la izquierda ('007') se conservan como string.
    """
    if not isinstance(value, str):
        return value
    if value == "":
        return 0 if empty_to_zero else default_blank
    if len(value) > 1 and value[0] == "0" and value.isdigit():
        return value  # preservar ceros a la izquierda (códigos, teléfonos)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def numericise_all(
    rows: list[list[Any]], *, empty_to_zero: bool = False, default_blank: Any = ""
) -> list[list[Any]]:
    """Aplica :func:`numericise` a cada celda de una matriz."""
    return [
        [numericise(cell, empty_to_zero=empty_to_zero, default_blank=default_blank) for cell in row]
        for row in rows
    ]


def numericise_records(
    records: list[dict[str, Any]], *, empty_to_zero: bool = False, default_blank: Any = ""
) -> list[dict[str, Any]]:
    """Aplica :func:`numericise` a los valores (no a las claves) de una lista de diccionarios."""
    return [
        {
            key: numericise(value, empty_to_zero=empty_to_zero, default_blank=default_blank)
            for key, value in record.items()
        }
        for record in records
    ]
