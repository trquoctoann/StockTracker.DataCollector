"""Unit tests for PipelineEngine."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.control.store import PipelineRunRecord, PipelineStore
from app.core.exceptions import PipelineBusyError, PipelineError
from app.engine.pipeline import PipelineEngine


async def _success_coro() -> None:
    pass


async def _failing_coro() -> None:
    raise ValueError("boom")


class FakePipelineStore:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []
        self.previous: PipelineRunRecord | None = None
        self.previous_steps: set[str] = set()

    @asynccontextmanager
    async def acquire_pipeline_lock(self, pipeline: str) -> AsyncIterator[None]:
        self.events.append(("lock", pipeline))
        yield

    async def get_run(self, run_id: UUID) -> PipelineRunRecord | None:
        self.events.append(("get_run", run_id))
        return self.previous

    async def completed_steps(self, run_id: UUID) -> set[str]:
        self.events.append(("completed_steps", run_id))
        return self.previous_steps

    async def start_run(self, run_id: UUID, pipeline: str, **kwargs: Any) -> None:
        self.events.append(("start_run", run_id, pipeline, kwargs))

    async def finish_run(self, run_id: UUID, status: str, **kwargs: Any) -> None:
        self.events.append(("finish_run", run_id, status, kwargs))

    async def heartbeat(self, run_id: UUID) -> None:
        self.events.append(("heartbeat", run_id))

    async def start_step(self, run_id: UUID, step_key: str, **kwargs: Any) -> None:
        self.events.append(("start_step", run_id, step_key, kwargs))

    async def finish_step(self, run_id: UUID, step_key: str, status: str, **kwargs: Any) -> None:
        self.events.append(("finish_step", run_id, step_key, status, kwargs))

    async def put_watermark(self, *args: Any, **kwargs: Any) -> None:
        self.events.append(("watermark", *args, kwargs))


@pytest.fixture(autouse=True)
def reset_pipeline_engine() -> Iterator[None]:
    PipelineEngine.configure(None)
    yield
    PipelineEngine.configure(None)


@pytest.mark.asyncio
async def test_pipeline_engine_success() -> None:
    """PipelineEngine.run should complete without raising on success."""
    await PipelineEngine.run("test_pipeline", _success_coro)


@pytest.mark.asyncio
async def test_pipeline_engine_wraps_exception() -> None:
    """PipelineEngine.run should wrap any exception into PipelineError."""
    with pytest.raises(PipelineError, match="test_pipeline"):
        await PipelineEngine.run("test_pipeline", _failing_coro)


@pytest.mark.asyncio
async def test_pipeline_engine_preserves_cause() -> None:
    """PipelineEngine.run should chain the original exception as __cause__."""
    with pytest.raises(PipelineError) as exc_info:
        await PipelineEngine.run("test_pipeline", _failing_coro)
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValueError)


@pytest.mark.asyncio
async def test_pipeline_engine_rejects_overlapping_run() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking() -> None:
        started.set()
        await release.wait()

    first = asyncio.create_task(PipelineEngine.run("exclusive_pipeline", blocking))
    await started.wait()
    with pytest.raises(PipelineBusyError):
        await PipelineEngine.run("exclusive_pipeline", _success_coro)
    release.set()
    await first


@pytest.mark.asyncio
async def test_pipeline_engine_persists_run_step_and_watermark() -> None:
    store = FakePipelineStore()
    PipelineEngine.configure(cast(PipelineStore, store))

    async def pipeline() -> None:
        async with PipelineEngine.step("prices:FPT") as should_run:
            assert should_run is True
            await PipelineEngine.put_watermark("prices", "FPT", {"date": "2026-08-30"}, source="KBS")

    run_id = await PipelineEngine.run("market", pipeline, trigger="test")

    assert any(event[:3] == ("finish_run", run_id, "completed") for event in store.events)
    assert any(event[:4] == ("finish_step", run_id, "prices:FPT", "completed") for event in store.events)
    assert any(event[0] == "watermark" for event in store.events)


@pytest.mark.asyncio
async def test_pipeline_resume_skips_completed_parent_steps() -> None:
    store = FakePipelineStore()
    parent_id = uuid4()
    now = datetime.now(UTC)
    store.previous = PipelineRunRecord(
        id=parent_id,
        pipeline="market",
        status="failed",
        trigger="api",
        submitted_at=now,
        started_at=now,
        heartbeat_at=now,
        finished_at=now,
        error="provider unavailable",
        resume_of=None,
    )
    store.previous_steps = {"prices:FPT"}
    PipelineEngine.configure(cast(PipelineStore, store))
    executed = False

    async def pipeline() -> None:
        nonlocal executed
        async with PipelineEngine.step("prices:FPT") as should_run:
            if should_run:
                executed = True

    run_id = await PipelineEngine.run("market", pipeline, trigger="api", resume_of=parent_id)

    assert executed is False
    assert any(event[:4] == ("finish_step", run_id, "prices:FPT", "skipped") for event in store.events)


@pytest.mark.asyncio
async def test_pipeline_resume_rejects_different_pipeline() -> None:
    store = FakePipelineStore()
    parent_id = uuid4()
    now = datetime.now(UTC)
    store.previous = PipelineRunRecord(
        id=parent_id,
        pipeline="listing",
        status="failed",
        trigger="api",
        submitted_at=now,
        started_at=now,
        heartbeat_at=now,
        finished_at=now,
        error="failed",
        resume_of=None,
    )
    PipelineEngine.configure(cast(PipelineStore, store))

    with pytest.raises(PipelineError, match="listing"):
        await PipelineEngine.run("market", _success_coro, resume_of=parent_id)
