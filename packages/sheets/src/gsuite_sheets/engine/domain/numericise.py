"""Inferencia de tipos de valores leídos (equivalente nativo de ``gspread.numericise``).

La Sheets API devuelve los valores como strings; estas funciones los convierten a ``int`` /
``float`` cuando corresponde. Conservan los strings con ceros a la izquierda (ej. códigos
postales o teléfonos) para no perder información.
"""

from __future__ import annotations

import math
import re
from typing import Any

# Solo ASCII y forma canónica: lo que Sheets mostraría como número, nada que Python
# además acepte (``1_000``, dígitos no ASCII, ``nan``/``inf``).
_INTEGER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
_LEADING_ZERO_DIGITS = re.compile(r"[+-]?0[0-9]+")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def numericise(value: Any, *, empty_to_zero: bool = False, default_blank: Any = "") -> Any:
    """Convierte ``value`` a ``int``/``float`` si es posible; si no, lo deja igual.

    - ``""`` -> ``0`` si ``empty_to_zero``, o ``default_blank`` en caso contrario.
    - Enteros ASCII canónicos (signo opcional, sin ceros a la izquierda; se toleran
      espacios alrededor) -> ``int``; decimales o notación científica ASCII -> ``float``
      finito.
    - Todo lo demás se devuelve sin cambios (el mismo objeto): strings con ceros a la
      izquierda ('007', '-007', ' 007': códigos, teléfonos), guiones bajos ('1_000'),
      dígitos no ASCII, 'nan'/'inf' y números que desbordan a infinito.
    """
    if not isinstance(value, str):
        return value
    if value == "":
        return 0 if empty_to_zero else default_blank
    text = value.strip()
    if _INTEGER.fullmatch(text):
        try:
            return int(text)
        except ValueError:  # supera el límite de dígitos de int(): se deja como texto
            return value
    if _LEADING_ZERO_DIGITS.fullmatch(text) or not _DECIMAL.fullmatch(text):
        return value  # preservar ceros a la izquierda y lo que no es un número ASCII
    number = float(text)
    return number if math.isfinite(number) else value


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
