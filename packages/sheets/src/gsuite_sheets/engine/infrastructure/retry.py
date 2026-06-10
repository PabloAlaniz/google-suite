"""Implementación de ``RetryPolicy``: backoff exponencial ante errores transitorios.

Opera sobre los ``ApiError`` del dominio (los adaptadores ya tradujeron el error del
transporte concreto), por lo que funciona igual con gspread, el cliente nativo o cualquier
otro backend. Esta es la pieza concreta que conoce el reloj (``time.sleep``); la capa de
aplicación depende del puerto ``RetryPolicy``, no de esta clase.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from gspreadmanager.domain.errors import ApiError

T = TypeVar("T")

logger = logging.getLogger(__name__)

# Códigos HTTP que justifican un reintento (cuota / sobrecarga temporal).
RETRYABLE_STATUS = {429, 500, 503}


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
            except ApiError as exc:  # noqa: PERF203  (try/except por intento es inherente al reintento)
                if exc.status_code not in RETRYABLE_STATUS or attempt >= self.max_retries:
                    raise
                delay = self.backoff * (2**attempt)
                logger.warning(
                    "Error transitorio de la API (HTTP %s); reintento %d/%d en %.1fs.",
                    exc.status_code,
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
                attempt += 1
