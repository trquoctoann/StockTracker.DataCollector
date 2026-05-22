from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from app.core.exceptions import PipelineError

_LOG = structlog.get_logger(__name__)


class PipelineEngine:
    @staticmethod
    async def run(name: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        _LOG.info("PIPELINE_START", pipeline=name)
        try:
            await coro_factory()
        except Exception as exc:
            _LOG.exception("PIPELINE_FAILED", pipeline=name, error=str(exc))
            raise PipelineError(f"Pipeline {name} failed: {exc}") from exc
        _LOG.info("PIPELINE_COMPLETE", pipeline=name)
