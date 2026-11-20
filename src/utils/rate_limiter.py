"""Simple semaphore-based rate limiter (Milestone 1).

Kept for M1 compatibility. From M2 onward fetchers take a pluggable
`RateLimitStrategy` (see src/strategies/rate_limit_strategy.py); this class
is a thin alias over `SemaphoreStrategy`.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from src.strategies.rate_limit_strategy import SemaphoreStrategy

T = TypeVar("T")


class RateLimiter(SemaphoreStrategy):
    """Limit how many coroutines run at the same time."""

    async def execute(self, coro: Awaitable[T]) -> T:
        async with self:
            return await coro
