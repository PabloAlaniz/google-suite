"""Implementación de ``RetryPolicy``: backoff exponencial ante errores transitorios.

Esta es la pieza concreta que conoce gspread (``APIError``) y el reloj (``time.sleep``).
La capa de aplicación depende del puerto ``RetryPolicy``, no de esta clase.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from gspread.exceptions import APIError

T = TypeVar("T")

# Códigos HTTP que justifican un reintento (cuota / sobrecarga temporal).
RETRYABLE_STATUS = {429, 500, 503}


def _status_code(error: APIError) -> int | None:
    """Extrae el código de estado HTTP de un APIError de gspread."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    code = getattr(error, "code", None)
    return code if isinstance(code, int) else None


class ExponentialBackoffRetry:
    """Política de reintentos con backoff exponencial (``backoff * 2**intento``).

    Solo reintenta ante códigos de estado transitorios (ver ``RETRYABLE_STATUS``);
    cualquier otro error se propaga de inmediato.
    """

    def __init__(self, max_retries: int = 3, backoff: float = 1.0) -> None:
        """Configura los reintentos máximos y el backoff base en segundos."""
        self.max_retries = max_retries
        self.backoff = backoff

    def run(self, operation: Callable[[], T]) -> T:
        """Ejecuta ``operation`` reintentando ante errores transitorios de la API."""
        attempt = 0
        while True:
            try:
                return operation()
            except APIError as exc:  # noqa: PERF203  (try/except por intento es inherente al reintento)
                status = _status_code(exc)
                if status not in RETRYABLE_STATUS or attempt >= self.max_retries:
                    raise
                time.sleep(self.backoff * (2**attempt))
                attempt += 1
