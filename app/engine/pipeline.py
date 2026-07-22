from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from app.core.exceptions import PipelineBusyError, PipelineError

_LOG = structlog.get_logger(__name__)


class PipelineEngine:
    _locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def is_running(cls, name: str) -> bool:
        lock = cls._locks.get(name)
        return lock is not None and lock.locked()

    @staticmethod
    async def run(name: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        lock = PipelineEngine._locks.setdefault(name, asyncio.Lock())
        if lock.locked():
            raise PipelineBusyError(f"Pipeline {name} is already running")
        async with lock:
            _LOG.info("PIPELINE_START", pipeline=name)
            try:
                await coro_factory()
            except PipelineError:
                raise
            except Exception as exc:
                _LOG.exception("PIPELINE_FAILED", pipeline=name, error=str(exc))
                raise PipelineError(f"Pipeline {name} failed: {exc}") from exc
            _LOG.info("PIPELINE_COMPLETE", pipeline=name)
