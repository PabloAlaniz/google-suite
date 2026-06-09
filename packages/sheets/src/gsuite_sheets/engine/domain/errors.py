"""Jerarquía de errores propia de GSpreadManager.

Hogar canónico de las excepciones. ``gspreadmanager.exceptions`` se conserva como
shim de compatibilidad que re-exporta ``GSpreadManagerError`` e ``InsertError``.
"""

from __future__ import annotations


class GSpreadManagerError(Exception):
    """Error base para todas las operaciones de GSpreadManager."""


class InsertError(GSpreadManagerError):
    """Se lanza cuando falla la inserción de datos en una hoja de cálculo."""


class InvalidColorError(GSpreadManagerError, ValueError):
    """Se lanza cuando un color no puede construirse (ej. hex inválido).

    Subclase de ``ValueError`` para mantener la compatibilidad con el código que
    captura ``ValueError`` al validar colores.
    """


class InvalidRangeError(GSpreadManagerError, ValueError):
    """Se lanza cuando un rango (A1 o GridRange) es inválido.

    Subclase de ``ValueError`` por compatibilidad.
    """


class InvalidIdentifierError(GSpreadManagerError, ValueError):
    """Se lanza cuando un identificador (documento, pestaña) es inválido.

    Subclase de ``ValueError`` por compatibilidad.
    """


class SchemaError(GSpreadManagerError, ValueError):
    """Se lanza cuando una fila no encaja con el modelo tipado (columna faltante o valor inválido).

    Subclase de ``ValueError`` por compatibilidad.
    """
