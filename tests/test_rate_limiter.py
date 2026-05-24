"""Unit tests for AsyncTokenBucket and RateLimiterRegistry."""

from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.core.rate_limiter import AsyncTokenBucket, RateLimiterRegistry

# ---------------------------------------------------------------------------
# AsyncTokenBucket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_bucket_allows_burst_then_throttles() -> None:
    """Burst capacity should be consumed immediately; 3rd token should require wait."""
    bucket = AsyncTokenBucket(rate_per_second=10.0, burst=2)
    t0 = time.monotonic()
    await bucket.acquire(1)
    await bucket.acquire(1)
    await bucket.acquire(1)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.08


@pytest.mark.asyncio
async def test_token_bucket_single_acquire_within_burst() -> None:
    """Single acquire on a full bucket should be near-instant."""
    bucket = AsyncTokenBucket(rate_per_second=1.0, burst=5)
    t0 = time.monotonic()
    await bucket.acquire(1)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1  # should be essentially instant


@pytest.mark.asyncio
async def test_token_bucket_invalid_rate_raises() -> None:
    """rate_per_second <= 0 should raise ValueError."""
    with pytest.raises(ValueError, match="rate_per_second"):
        AsyncTokenBucket(rate_per_second=0.0, burst=5)

    with pytest.raises(ValueError, match="rate_per_second"):
        AsyncTokenBucket(rate_per_second=-1.0, burst=5)


@pytest.mark.asyncio
async def test_token_bucket_invalid_burst_raises() -> None:
    """burst < 1 should raise ValueError."""
    with pytest.raises(ValueError, match="burst"):
        AsyncTokenBucket(rate_per_second=1.0, burst=0)


# ---------------------------------------------------------------------------
# RateLimiterRegistry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_acquire_unknown_falls_back_to_http() -> None:
    """Acquiring with unknown key should fall back to 'http' bucket."""
    s = Settings()
    reg = RateLimiterRegistry(s)
    await reg.acquire("nonexistent_key")
    await reg.acquire("http")


@pytest.mark.asyncio
async def test_registry_known_keys_exist() -> None:
    """Registry should have 'vnstock', 'http', and 'rabbitmq' buckets by default."""
    s = Settings()
    reg = RateLimiterRegistry(s)
    # Should not raise
    await reg.acquire("vnstock")
    await reg.acquire("http")
    await reg.acquire("rabbitmq")


@pytest.mark.asyncio
async def test_registry_register_custom_bucket() -> None:
    """register() should allow creating a new named bucket."""
    s = Settings()
    reg = RateLimiterRegistry(s)
    reg.register("custom", rate_per_second=100.0, burst=50)
    # Should use the registered custom bucket, not fall back to http
    await reg.acquire("custom")
