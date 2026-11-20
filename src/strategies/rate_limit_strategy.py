"""Rate limiting strategies (M2: Strategy pattern).

Fetchers depend on the `RateLimitStrategy` abstraction, so each source can
use a different policy without the fetcher code changing.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod


class RateLimitStrategy(ABC):
    """Acquire before a request, release after. Usable as `async with`."""

    @abstractmethod
    async def acquire(self) -> None: ...

    @abstractmethod
    def release(self) -> None: ...

    async def __aenter__(self) -> RateLimitStrategy:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


class SemaphoreStrategy(RateLimitStrategy):
    """Cap the number of in-flight requests."""

    def __init__(self, max_concurrent: int = 10):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def acquire(self) -> None:
        await self.semaphore.acquire()

    def release(self) -> None:
        self.semaphore.release()


class TokenBucketStrategy(RateLimitStrategy):
    """Allow `rate` requests per `per` seconds, with bursts up to `rate`."""

    def __init__(self, rate: int, per: float):
        if rate < 1 or per <= 0:
            raise ValueError("rate must be >= 1 and per > 0")
        self.rate = rate
        self.per = per
        self.allowance = float(rate)
        self.last_check = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        # The lock makes refill+spend atomic across concurrent callers.
        async with self._lock:
            while True:
                now = time.monotonic()
                self.allowance = min(
                    self.rate, self.allowance + (now - self.last_check) * self.rate / self.per
                )
                self.last_check = now
                if self.allowance >= 1.0:
                    self.allowance -= 1.0
                    return
                await asyncio.sleep((1.0 - self.allowance) * self.per / self.rate)

    def release(self) -> None:
        """Tokens refill over time; nothing to release."""


class NoRateLimitStrategy(RateLimitStrategy):
    """Null object — handy for tests and single-request sources."""

    async def acquire(self) -> None:
        return None

    def release(self) -> None:
        return None
