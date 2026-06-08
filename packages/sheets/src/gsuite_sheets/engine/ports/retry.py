"""Puerto de la política de reintentos.

Abstrae el reintento del transporte concreto: la capa de aplicación ejecuta sus
operaciones a través de una ``RetryPolicy`` inyectada, sin conocer gspread ni los
detalles del backoff.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class RetryPolicy(Protocol):
    """Ejecuta una operación aplicando una política de reintentos."""

    def run(self, operation: Callable[[], T]) -> T:
        """Ejecuta ``operation`` y la reintenta según la política; devuelve su resultado."""
        ...
