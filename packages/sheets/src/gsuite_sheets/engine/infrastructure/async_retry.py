"""``AsyncRetryPolicy``: backoff exponencial con ``asyncio.sleep`` (sin bloquear el loop).

Espejo async de ``infrastructure.retry``: opera sobre los mismos ``ApiError`` del dominio
y los mismos códigos transitorios (``RETRYABLE_STATUS``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from gspreadmanager.domain.errors import ApiError
from gspreadmanager.infrastructure.retry import RETRYABLE_STATUS

T = TypeVar("T")

logger = logging.getLogger(__name__)


class AsyncExponentialBackoffRetry:
    """Reintentos con backoff exponencial (``backoff * 2**intento``), versión async."""

    def __init__(self, max_retries: int = 3, backoff: float = 1.0) -> None:
        """Configura los reintentos máximos y el backoff base en segundos."""
        self.max_retries = max_retries
        self.backoff = backoff

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Ejecuta ``operation`` reintentando ante errores transitorios de la API."""
        attempt = 0
        while True:
            try:
                return await operation()
            except ApiError as exc:  # noqa: PERF203  (try/except por intento es inherente)
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
                await asyncio.sleep(delay)
                attempt += 1
