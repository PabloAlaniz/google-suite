"""Tests del limitador de tasa (token bucket) y su cableado en el facade."""

from __future__ import annotations

from typing import Any

import pytest
from gspreadmanager import GSpreadManagerError, SheetManager
from gspreadmanager.infrastructure.rate_limit import TokenBucketRateLimiter
from gspreadmanager.retry import retry_on_rate_limit
from gspreadmanager.testing import InMemoryBackend


class FakeClock:
    """Reloj falso: ``sleep`` adelanta el tiempo (sin esperar de verdad)."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _limiter(
    rate: float, capacity: float | None = None
) -> tuple[TokenBucketRateLimiter, FakeClock]:
    clock = FakeClock()
    rl = TokenBucketRateLimiter(rate, capacity, clock=clock.now, sleep=clock.sleep)
    return rl, clock


class TestTokenBucket:
    def test_initial_burst_is_instant(self):
        rl, clock = _limiter(2.0, 2.0)
        for _ in range(2):
            rl.acquire()
        assert clock.t == 0.0  # arranca lleno: 2 permisos sin esperar

    def test_sustained_rate(self):
        rl, clock = _limiter(2.0, 2.0)
        times = []
        for _ in range(5):
            rl.acquire()
            times.append(round(clock.t, 3))
        assert times == [0.0, 0.0, 0.5, 1.0, 1.5]

    def test_sub_one_rate_allows_single_then_waits(self):
        rl, clock = _limiter(0.5)  # capacity por defecto = max(1, 0.5) = 1
        rl.acquire()
        assert clock.t == 0.0
        rl.acquire()
        assert clock.t == 2.0  # 1 token / 0.5 por seg = 2 seg

    def test_capacity_caps_accumulation(self):
        rl, clock = _limiter(10.0, 2.0)
        clock.t = 100.0  # mucho tiempo ocioso, pero el bucket no pasa de capacity=2
        rl.acquire()
        rl.acquire()
        assert clock.t == 100.0
        rl.acquire()
        assert round(clock.t - 100.0, 3) == 0.1  # el 3º espera 1/10 s

    def test_invalid_rate_raises(self):
        with pytest.raises(GSpreadManagerError, match="rate_limit"):
            TokenBucketRateLimiter(0)

    def test_default_capacity(self):
        assert TokenBucketRateLimiter(5.0).capacity == 5.0
        assert TokenBucketRateLimiter(0.2).capacity == 1.0


class CountingLimiter:
    def __init__(self) -> None:
        self.acquired = 0

    def acquire(self) -> None:
        self.acquired += 1


class _Spy:
    def __init__(self, limiter: Any) -> None:
        self._rate_limiter = limiter
        self.max_retries = 0
        self.retry_backoff = 1.0
        self.calls: list[int] = []

    @retry_on_rate_limit
    def op(self, value: int) -> int:
        self.calls.append(value)
        return value * 2


class TestDecoratorWiring:
    def test_acquires_a_permit_per_call(self):
        limiter = CountingLimiter()
        spy = _Spy(limiter)
        assert spy.op(3) == 6
        assert spy.op(4) == 8
        assert limiter.acquired == 2
        assert spy.calls == [3, 4]

    def test_no_limiter_runs_normally(self):
        spy = _Spy(None)
        assert spy.op(5) == 10
        assert spy.calls == [5]

    def test_acquire_happens_before_operation(self):
        class Boom(CountingLimiter):
            def acquire(self) -> None:
                super().acquire()
                raise RuntimeError("sin cupo")

        spy = _Spy(Boom())
        with pytest.raises(RuntimeError, match="sin cupo"):
            spy.op(1)
        assert spy.calls == []  # no se ejecutó la operación


class TestFacadeIntegration:
    @pytest.fixture
    def backend(self):
        b = InMemoryBackend()
        b.add_spreadsheet("Doc", {"H": [["a", "b"], ["1", "2"]]})
        return b

    def test_operations_work_with_rate_limit(self, backend):
        # rate alto: no espera de verdad en el test, pero ejercita el camino del limiter.
        mgr = SheetManager("Doc", sheets_client=backend.client, rate_limit=1000)
        ws = mgr.worksheet("H")
        assert ws.read() == [["a", "b"], ["1", "2"]]
        ws.update_cell(1, 1, "z")
        assert ws.read()[0][0] == "z"

    def test_manager_and_worksheet_share_one_bucket(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, rate_limit=1000)
        assert mgr._rate_limiter is mgr.worksheet("H")._rate_limiter

    def test_disabled_by_default(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client)
        assert mgr._rate_limiter is None

    def test_burst_override(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, rate_limit=5, rate_limit_burst=20)
        assert isinstance(mgr._rate_limiter, TokenBucketRateLimiter)
        assert mgr._rate_limiter.capacity == 20.0

    def test_combines_with_cache(self, backend):
        mgr = SheetManager("Doc", sheets_client=backend.client, rate_limit=1000, cache=True)
        ws = mgr.worksheet("H")
        assert ws.read() == [["a", "b"], ["1", "2"]]
        ws.append([["3", "4"]])
        assert ws.read()[-1] == ["3", "4"]
