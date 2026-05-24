"""Unit tests for PipelineEngine."""

from __future__ import annotations

import pytest

from app.core.exceptions import PipelineError
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
