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


class ApiError(GSpreadManagerError):
    """Error devuelto por la API de Google (Sheets/Drive), con su código HTTP si se conoce.

    Es el contrato que ven la política de reintentos y el usuario: los adaptadores traducen
    los errores del transporte concreto (gspread, cliente nativo) a esta jerarquía.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Guarda el mensaje y el código de estado HTTP (si se conoce)."""
        super().__init__(message)
        self.status_code = status_code


class QuotaExceededError(ApiError):
    """Cuota de la API excedida (HTTP 429). Es transitorio: el retry lo reintenta."""


class PermissionDeniedError(ApiError):
    """Sin permisos sobre el recurso (HTTP 403, salvo cuota)."""


class SpreadsheetNotFoundError(ApiError):
    """No se encontró el documento (por nombre, key o URL)."""


class WorksheetNotFoundError(ApiError):
    """No existe la pestaña pedida en el documento."""


class CellNotFoundError(GSpreadManagerError):
    """No se encontró la celda buscada (``find``)."""


_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_FORBIDDEN = 403


def api_error_from_status(status_code: int | None, message: str) -> ApiError:
    """Construye el ``ApiError`` más específico según el código de estado HTTP."""
    if status_code == _HTTP_TOO_MANY_REQUESTS:
        return QuotaExceededError(message, status_code)
    if status_code == _HTTP_FORBIDDEN:
        return PermissionDeniedError(message, status_code)
    return ApiError(message, status_code)
