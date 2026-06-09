"""Implementación de ``RateLimiter``: token bucket proactivo.

Frena las operaciones para no exceder una tasa sostenida (``rate`` permisos por segundo),
admitiendo ráfagas hasta ``capacity``. Es la pieza concreta que conoce el reloj y el sleep
(inyectables para tests); la capa de aplicación depende del puerto ``RateLimiter``.

A diferencia del ``RetryPolicy`` (que reacciona a un 429 ya ocurrido), esto evita pegarle a
la cuota: espera *antes* de la operación si no hay cupo.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from gspreadmanager.domain.errors import GSpreadManagerError


class TokenBucketRateLimiter:
    """Token bucket: ``rate`` permisos/seg sostenidos, con ráfaga de hasta ``capacity``.

    El bucket arranca lleno (permite una ráfaga inicial de ``capacity``). Cada ``acquire``
    consume un token; si no hay, espera lo justo para que se recargue uno. Es thread-safe.
    """

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configura la tasa (permisos/seg) y la capacidad (ráfaga, por defecto ``max(1, rate)``)."""
        if rate <= 0:
            raise GSpreadManagerError("El rate_limit debe ser mayor que 0.")
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity
        self._timestamp = clock()
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Consume un permiso, esperando si el bucket está vacío."""
        with self._lock:
            self._refill()
            if self._tokens < 1.0:
                self._sleep((1.0 - self._tokens) / self.rate)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        """Acredita los tokens generados desde la última lectura del reloj."""
        now = self._clock()
        elapsed = now - self._timestamp
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._timestamp = now
