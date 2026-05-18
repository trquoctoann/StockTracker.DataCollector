from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from app.core.config import Settings


@dataclass
class _BucketState:
    tokens: float
    last_ts: float


class AsyncTokenBucket:
    def __init__(self, rate_per_second: float, burst: int) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self._rate = rate_per_second
        self._burst = float(burst)
        self._state = _BucketState(tokens=self._burst, last_ts=time.monotonic())
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        while True:
            wait_for: float
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._state.last_ts
                self._state.tokens = min(self._burst, self._state.tokens + elapsed * self._rate)
                self._state.last_ts = now
                if self._state.tokens >= tokens:
                    self._state.tokens -= tokens
                    return
                deficit = tokens - self._state.tokens
                wait_for = deficit / self._rate
            await asyncio.sleep(wait_for)


class RateLimiterRegistry:
    def __init__(self, settings: Settings) -> None:
        self._buckets: dict[str, AsyncTokenBucket] = {
            "vnstock": AsyncTokenBucket(
                settings.rate_limit_vnstock_per_second,
                settings.rate_limit_vnstock_burst,
            ),
            "http": AsyncTokenBucket(
                settings.rate_limit_http_per_second,
                settings.rate_limit_http_burst,
            ),
            "rabbitmq": AsyncTokenBucket(
                settings.rate_limit_rabbitmq_per_second,
                settings.rate_limit_rabbitmq_burst,
            ),
        }

    def register(self, key: str, rate_per_second: float, burst: int) -> None:
        self._buckets[key] = AsyncTokenBucket(rate_per_second, burst)

    async def acquire(self, source_key: str, tokens: float = 1.0) -> None:
        bucket = self._buckets.get(source_key)
        if bucket is None:
            bucket = self._buckets["http"]
        await bucket.acquire(tokens)
