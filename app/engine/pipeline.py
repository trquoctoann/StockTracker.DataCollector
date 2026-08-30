from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import structlog

from app.control.context import (
    PipelineRunContext,
    get_pipeline_run_context,
    reset_pipeline_run_context,
    set_pipeline_run_context,
)
from app.control.store import PipelineStore
from app.core.exceptions import PipelineBusyError, PipelineError
from app.middleware.metrics import HttpMetrics

_LOG = structlog.get_logger(__name__)


class PipelineEngine:
    _locks: dict[str, asyncio.Lock] = {}
    _store: PipelineStore | None = None
    _heartbeat_seconds: int = 30
    _metrics: HttpMetrics | None = None

    @classmethod
    def configure(
        cls,
        store: PipelineStore | None,
        *,
        heartbeat_seconds: int = 30,
        metrics: HttpMetrics | None = None,
    ) -> None:
        cls._store = store
        cls._heartbeat_seconds = heartbeat_seconds
        cls._metrics = metrics

    @classmethod
    def is_running(cls, name: str) -> bool:
        lock = cls._locks.get(name)
        return lock is not None and lock.locked()

    @classmethod
    async def run(
        cls,
        name: str,
        coro_factory: Callable[[], Awaitable[None]],
        *,
        run_id: UUID | None = None,
        trigger: str = "internal",
        resume_of: UUID | None = None,
    ) -> UUID:
        local_lock = cls._locks.setdefault(name, asyncio.Lock())
        if local_lock.locked():
            raise PipelineBusyError(f"Pipeline {name} is already running")
        resolved_run_id = run_id or uuid4()
        async with local_lock:
            if cls._store is None:
                await cls._execute(name, resolved_run_id, coro_factory, trigger=trigger, resume_of=resume_of)
            else:
                async with cls._store.acquire_pipeline_lock(name):
                    await cls._execute(name, resolved_run_id, coro_factory, trigger=trigger, resume_of=resume_of)
        return resolved_run_id

    @classmethod
    async def _execute(
        cls,
        name: str,
        run_id: UUID,
        coro_factory: Callable[[], Awaitable[None]],
        *,
        trigger: str,
        resume_of: UUID | None,
    ) -> None:
        completed_steps: frozenset[str] = frozenset()
        heartbeat_task: asyncio.Task[None] | None = None
        token = None
        started_at = time.monotonic()
        terminal_status = "failed"
        try:
            if cls._store is not None:
                if resume_of is not None:
                    previous_run = await cls._store.get_run(resume_of)
                    if previous_run is None:
                        raise PipelineError(f"Cannot resume missing pipeline run {resume_of}")
                    if previous_run.pipeline != name:
                        raise PipelineError(f"Cannot resume {name} from a {previous_run.pipeline} pipeline run")
                    if previous_run.status not in {"failed", "cancelled", "abandoned"}:
                        raise PipelineError(f"Cannot resume pipeline run {resume_of} with status {previous_run.status}")
                    completed_steps = frozenset(await cls._store.completed_steps(resume_of))
                await cls._store.start_run(run_id, name, trigger=trigger, resume_of=resume_of)
                heartbeat_task = asyncio.create_task(cls._heartbeat_loop(run_id))
            elif resume_of is not None:
                raise PipelineError("Pipeline resume requires the durable control plane")

            token = set_pipeline_run_context(
                PipelineRunContext(
                    run_id=run_id,
                    pipeline=name,
                    resume_of=resume_of,
                    completed_steps=completed_steps,
                )
            )

            _LOG.info("PIPELINE_START", pipeline=name, run_id=str(run_id), trigger=trigger)
            try:
                await coro_factory()
            except asyncio.CancelledError:
                terminal_status = "cancelled"
                if cls._store is not None:
                    await cls._store.finish_run(run_id, "cancelled", error="pipeline task cancelled")
                _LOG.warning("PIPELINE_CANCELLED", pipeline=name, run_id=str(run_id))
                raise
            except PipelineError as exc:
                terminal_status = "failed"
                if cls._store is not None:
                    await cls._store.finish_run(run_id, "failed", error=str(exc))
                raise
            except Exception as exc:
                terminal_status = "failed"
                if cls._store is not None:
                    await cls._store.finish_run(run_id, "failed", error=str(exc))
                _LOG.exception("PIPELINE_FAILED", pipeline=name, run_id=str(run_id), error=str(exc))
                raise PipelineError(f"Pipeline {name} failed: {exc}") from exc
            else:
                terminal_status = "completed"
                if cls._store is not None:
                    await cls._store.finish_run(run_id, "completed")
                _LOG.info("PIPELINE_COMPLETE", pipeline=name, run_id=str(run_id))
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
            if token is not None:
                reset_pipeline_run_context(token)
            if cls._metrics is not None:
                cls._metrics.observe_pipeline(name, terminal_status, time.monotonic() - started_at, time.time())

    @classmethod
    async def _heartbeat_loop(cls, run_id: UUID) -> None:
        assert cls._store is not None
        while True:
            await asyncio.sleep(cls._heartbeat_seconds)
            try:
                await cls._store.heartbeat(run_id)
            except Exception:
                _LOG.exception("PIPELINE_HEARTBEAT_FAILED", run_id=str(run_id))

    @classmethod
    @asynccontextmanager
    async def step(cls, step_key: str, *, metadata: Mapping[str, Any] | None = None) -> AsyncIterator[bool]:
        context = get_pipeline_run_context()
        should_run = context is None or step_key not in context.completed_steps
        if cls._store is not None and context is not None:
            await cls._store.start_step(context.run_id, step_key, metadata=metadata)
            if not should_run:
                await cls._store.finish_step(context.run_id, step_key, "skipped")
        try:
            yield should_run
        except BaseException as exc:
            if cls._store is not None and context is not None and should_run:
                await cls._store.finish_step(context.run_id, step_key, "failed", error=str(exc))
            raise
        else:
            if cls._store is not None and context is not None and should_run:
                await cls._store.finish_step(context.run_id, step_key, "completed")

    @classmethod
    async def put_watermark(
        cls,
        stream: str,
        partition_key: str,
        cursor: Mapping[str, Any],
        *,
        source: str | None,
    ) -> None:
        context = get_pipeline_run_context()
        if cls._store is None or context is None:
            return
        await cls._store.put_watermark(
            context.pipeline,
            stream,
            partition_key,
            cursor,
            source=source,
            run_id=context.run_id,
        )
