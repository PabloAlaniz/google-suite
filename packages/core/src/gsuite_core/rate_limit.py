"""Proactive rate limiting: a token bucket shared by sync and async requests.

Retries react to 429s after the fact; the bucket keeps a process under a rate
(GSUITE_RATE_LIMIT requests per second) so it rarely gets them. Disabled by
default. Adapted from GSpreadManager's token buckets (sync and async).
"""

import asyncio
import threading
import time
from functools import lru_cache


class TokenBucket:
    """``rate`` tokens per second, up to ``burst``; one token per request."""

    def __init__(self, rate: float, burst: float | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.burst = burst if burst is not None else max(1.0, rate)
        self._tokens = self.burst
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def _take(self) -> float:
        """Take a token if available; otherwise return the seconds to wait for one."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self.burst, self._tokens + (now - self._updated) * self.rate)
            self._updated = now
            if self._tokens >= 1:
                self._tokens -= 1
                return 0.0
            return (1 - self._tokens) / self.rate

    def acquire(self) -> None:
        """Block (sleeping) until a token is available."""
        while (wait := self._take()) > 0:
            time.sleep(wait)

    async def acquire_async(self) -> None:
        """Wait (without blocking the event loop) until a token is available."""
        while (wait := self._take()) > 0:
            await asyncio.sleep(wait)


@lru_cache
def _limiter(rate: float, burst: float | None) -> TokenBucket:
    return TokenBucket(rate, burst)


def get_rate_limiter() -> TokenBucket | None:
    """The process-wide bucket from settings, or None when rate limiting is off."""
    from gsuite_core.config import get_settings

    settings = get_settings()
    if settings.rate_limit is None:
        return None
    return _limiter(settings.rate_limit, settings.rate_limit_burst)
