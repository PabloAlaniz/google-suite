"""``AsyncRateLimiter``: token bucket cooperativo con ``asyncio.sleep``.

Espejo async de ``infrastructure.rate_limit``: misma semántica (``rate`` permisos/seg
sostenidos, ráfaga hasta ``capacity``), pero la espera cede el control al event loop en
vez de bloquear el thread.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from gspreadmanager.domain.errors import GSpreadManagerError

logger = logging.getLogger(__name__)


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class AsyncTokenBucketRateLimiter:
    """Token bucket async: arranca lleno; ``acquire`` espera (sin bloquear) si no hay cupo."""

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = _default_sleep,
    ) -> None:
        """Configura la tasa (permisos/seg) y la capacidad (ráfaga, default ``max(1, rate)``)."""
        if rate <= 0:
            raise GSpreadManagerError("El rate_limit debe ser mayor que 0.")
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity
        self._timestamp = clock()
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Consume un permiso, esperando cooperativamente si el bucket está vacío."""
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                logger.debug("Rate limit (async): esperando %.3fs por un permiso.", wait)
                await self._sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        """Acredita los tokens generados desde la última lectura del reloj."""
        now = self._clock()
        elapsed = now - self._timestamp
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._timestamp = now
