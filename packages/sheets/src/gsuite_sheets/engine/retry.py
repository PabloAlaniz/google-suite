"""Decorador de reintento para los métodos del facade.

La lógica vive en ``infrastructure.retry.ExponentialBackoffRetry`` (una ``RetryPolicy``).
Este decorador la aplica a los métodos de ``SheetManager`` / ``WorksheetContext``, que
exponen ``max_retries``/``retry_backoff`` en la instancia.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .infrastructure.retry import RETRYABLE_STATUS, ExponentialBackoffRetry, _status_code

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["RETRYABLE_STATUS", "ExponentialBackoffRetry", "_status_code", "retry_on_rate_limit"]


def retry_on_rate_limit(func: F) -> F:
    """Aplica freno de tasa proactivo + reintento reactivo al método decorado.

    Si la instancia (``SheetManager`` / ``WorksheetContext``) tiene un ``_rate_limiter``,
    pide un permiso antes de operar (token bucket). Luego ejecuta a través de una
    ``ExponentialBackoffRetry`` construida con ``max_retries`` y ``retry_backoff``.
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        limiter = getattr(self, "_rate_limiter", None)
        if limiter is not None:
            limiter.acquire()
        policy = ExponentialBackoffRetry(
            max_retries=getattr(self, "max_retries", 0),
            backoff=getattr(self, "retry_backoff", 1.0),
        )
        return policy.run(lambda: func(self, *args, **kwargs))

    return wrapper  # type: ignore[return-value]
