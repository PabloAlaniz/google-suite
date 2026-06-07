"""Utilidades de reintento con backoff exponencial ante límites de cuota de la API."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from gspread.exceptions import APIError

F = TypeVar("F", bound=Callable[..., Any])

# Códigos HTTP que justifican un reintento (cuota / sobrecarga temporal).
RETRYABLE_STATUS = {429, 500, 503}


def _status_code(error: APIError) -> int | None:
    """Extrae el código de estado HTTP de un APIError de gspread."""
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status is not None:
        return status
    return getattr(error, "code", None)


def retry_on_rate_limit(func: F) -> F:
    """Reintenta el método decorado ante errores transitorios de la API.

    Lee la configuración (`max_retries` y `retry_backoff`) de la instancia, por lo
    que está pensado para métodos de `GoogleSheetConector`. Solo reintenta ante
    códigos de estado considerados transitorios (ver ``RETRYABLE_STATUS``); cualquier
    otro error se propaga inmediatamente.
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        max_retries: int = getattr(self, "max_retries", 0)
        backoff: float = getattr(self, "retry_backoff", 1.0)
        attempt = 0
        while True:
            try:
                return func(self, *args, **kwargs)
            except APIError as exc:
                status = _status_code(exc)
                if status not in RETRYABLE_STATUS or attempt >= max_retries:
                    raise
                time.sleep(backoff * (2**attempt))
                attempt += 1

    return wrapper  # type: ignore[return-value]
