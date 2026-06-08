"""Decorador de reintento (transitorio/compat).

La lógica vive ahora en ``infrastructure.retry.ExponentialBackoffRetry`` (una
``RetryPolicy``). Este decorador se conserva para los métodos de ``GoogleSheetConector``
que aún leen ``max_retries``/``retry_backoff`` de la instancia; se reemplazará por una
``RetryPolicy`` inyectada cuando el conector se descomponga en servicios (Sprint 5).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .infrastructure.retry import RETRYABLE_STATUS, ExponentialBackoffRetry, _status_code

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["RETRYABLE_STATUS", "ExponentialBackoffRetry", "_status_code", "retry_on_rate_limit"]


def retry_on_rate_limit(func: F) -> F:
    """Reintenta el método decorado delegando en una ``ExponentialBackoffRetry``.

    Construye la política a partir de ``max_retries`` y ``retry_backoff`` de la
    instancia, por lo que está pensado para métodos de ``GoogleSheetConector``.
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        policy = ExponentialBackoffRetry(
            max_retries=getattr(self, "max_retries", 0),
            backoff=getattr(self, "retry_backoff", 1.0),
        )
        return policy.run(lambda: func(self, *args, **kwargs))

    return wrapper  # type: ignore[return-value]
