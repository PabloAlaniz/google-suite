"""Puerto del limitador de tasa (rate limiter).

Abstrae el control proactivo de cuota: el facade pide un permiso antes de cada operación a
través de un ``RateLimiter`` inyectado, sin conocer la estrategia concreta (token bucket u
otra). Complementa al ``RetryPolicy`` (reactivo, ante 429) con un freno preventivo.
"""

from __future__ import annotations

from typing import Protocol


class RateLimiter(Protocol):
    """Concede permiso para realizar una operación, esperando si haría falta."""

    def acquire(self) -> None:
        """Bloquea hasta que haya cupo para una operación (consume un permiso)."""
        ...


class AsyncRateLimiter(Protocol):
    """Versión async del freno de tasa: espera con ``asyncio.sleep`` (sin bloquear)."""

    async def acquire(self) -> None:
        """Consume un permiso, esperando de forma cooperativa si no hay cupo."""
        ...
