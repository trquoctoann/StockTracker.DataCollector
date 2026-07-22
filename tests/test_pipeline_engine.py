"""Unit tests for PipelineEngine."""

from __future__ import annotations

import asyncio

import pytest

from app.core.exceptions import PipelineBusyError, PipelineError
from app.engine.pipeline import PipelineEngine


async def _success_coro() -> None:
    pass


async def _failing_coro() -> None:
    raise ValueError("boom")


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
