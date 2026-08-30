from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.core.exceptions import PipelineBusyError
from app.engine.pipeline import PipelineEngine


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


class PipelineJob(BaseModel):
    id: UUID
    pipeline: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class JobRegistry:
    def __init__(self, max_retained_jobs: int = 1_000) -> None:
        if max_retained_jobs < 1:
            raise ValueError("max_retained_jobs must be at least 1")
        self._max_retained_jobs = max_retained_jobs
        self._jobs: dict[UUID, PipelineJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._pending_pipelines: set[str] = set()

    def submit(
        self,
        pipeline: str,
        factory: Callable[[], Awaitable[None]],
        *,
        resume_of: UUID | None = None,
    ) -> PipelineJob:
        if pipeline in self._pending_pipelines or PipelineEngine.is_running(pipeline):
            raise PipelineBusyError(f"Pipeline {pipeline} is already queued or running")
        job = PipelineJob(
            id=uuid4(),
            pipeline=pipeline,
            status=JobStatus.PENDING,
            submitted_at=datetime.now(UTC),
        )
        self._jobs[job.id] = job
        self._pending_pipelines.add(pipeline)
        task = asyncio.create_task(self._run(job, factory, resume_of=resume_of))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job.model_copy(deep=True)

    def get(self, job_id: UUID) -> PipelineJob | None:
        job = self._jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(
        self,
        job: PipelineJob,
        factory: Callable[[], Awaitable[None]],
        *,
        resume_of: UUID | None,
    ) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        try:
            await PipelineEngine.run(
                job.pipeline,
                factory,
                run_id=job.id,
                trigger="api",
                resume_of=resume_of,
            )
            job.status = JobStatus.COMPLETED
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.error = "pipeline task cancelled"
            raise
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
        finally:
            job.finished_at = datetime.now(UTC)
            self._pending_pipelines.discard(job.pipeline)
            self._prune_terminal_jobs()

    def _prune_terminal_jobs(self) -> None:
        terminal_job_ids = [job_id for job_id, job in self._jobs.items() if job.finished_at is not None]
        excess = len(terminal_job_ids) - self._max_retained_jobs
        for job_id in terminal_job_ids[: max(0, excess)]:
            self._jobs.pop(job_id, None)
