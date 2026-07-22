import asyncio

import pytest

from app.core.exceptions import PipelineBusyError
from app.engine.job_registry import JobRegistry, JobStatus


@pytest.mark.asyncio
async def test_job_registry_tracks_completion() -> None:
    registry = JobRegistry()
    completed = asyncio.Event()

    async def work() -> None:
        completed.set()

    submitted = registry.submit("listing", work)
    await completed.wait()
    await asyncio.sleep(0)

    job = registry.get(submitted.id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.started_at is not None
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_job_registry_rejects_duplicate_pending_pipeline() -> None:
    registry = JobRegistry()
    release = asyncio.Event()

    async def work() -> None:
        await release.wait()

    registry.submit("listing", work)
    with pytest.raises(PipelineBusyError):
        registry.submit("listing", work)
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
