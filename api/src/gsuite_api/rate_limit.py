"""The REST API's request budget, on omnilimit.

One bucket shared by every client: the API has a single key, and behind a proxy the client
address is the proxy's. In memory each process counts on its own; with Redis, every instance
shares the budget.
"""

from fractions import Fraction

from omnilimit import Limiter, MemoryStore, OnStoreError, Store

from gsuite_core import Settings

_SLOWEST_RATE = Fraction(1, 1_000_000)
_REDIS_TIMEOUT_S = 0.25
# Connecting and then answering can each take the socket timeout.
_STORE_TIMEOUT_MS = 600


def to_policy(rate: float, burst: float | None) -> tuple[int, int, int]:
    """Turn requests per second into omnilimit's integers: (limit, window_ms, burst)."""
    exact = max(Fraction(rate).limit_denominator(1_000_000), _SLOWEST_RATE)
    # A fractional request can never be served at once, so burst rounds down.
    allowed_at_once = max(1, int(burst if burst is not None else rate))
    return exact.numerator, exact.denominator * 1000, allowed_at_once


def _redis_store(url: str) -> Store:
    try:
        from redis import Redis
    except ImportError as exc:
        raise RuntimeError(
            "GSUITE_API_RATE_LIMIT_REDIS_URL needs the redis package: "
            'pip install "gsuite-sdk[api,cloudrun]"'
        ) from exc
    from omnilimit.stores.redis import RedisStore

    client = Redis.from_url(
        url, socket_timeout=_REDIS_TIMEOUT_S, socket_connect_timeout=_REDIS_TIMEOUT_S
    )
    return RedisStore(client)


def build_limiter(settings: Settings) -> Limiter | None:
    """The app's limiter, or None when the rate limit is off."""
    if not settings.api_rate_limit:
        return None
    limit, window_ms, burst = to_policy(settings.api_rate_limit, settings.api_rate_limit_burst)
    url = settings.api_rate_limit_redis_url
    store: Store = _redis_store(url.get_secret_value()) if url else MemoryStore()
    # Settings requires a mode with Redis, and the memory store cannot fail.
    on_store_error: OnStoreError = settings.api_rate_limit_on_store_error or "closed"
    return Limiter(
        store=store,
        scope="gsuite-api",
        limit=limit,
        window_ms=window_ms,
        burst=burst,
        on_store_error=on_store_error,
        store_timeout_ms=_STORE_TIMEOUT_MS,
    )
