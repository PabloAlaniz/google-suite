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
    """Reintenta el método decorado delegando en una ``ExponentialBackoffRetry``.

    Construye la política a partir de ``max_retries`` y ``retry_backoff`` de la instancia
    (``SheetManager`` / ``WorksheetContext``).
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        policy = ExponentialBackoffRetry(
            max_retries=getattr(self, "max_retries", 0),
            backoff=getattr(self, "retry_backoff", 1.0),
        )
        return policy.run(lambda: func(self, *args, **kwargs))

    return wrapper  # type: ignore[return-value]
