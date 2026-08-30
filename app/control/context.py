from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PipelineRunContext:
    run_id: UUID
    pipeline: str
    resume_of: UUID | None = None
    completed_steps: frozenset[str] = frozenset()


_current_run: ContextVar[PipelineRunContext | None] = ContextVar("pipeline_run", default=None)


def get_pipeline_run_context() -> PipelineRunContext | None:
    return _current_run.get()


def set_pipeline_run_context(context: PipelineRunContext) -> Token[PipelineRunContext | None]:
    return _current_run.set(context)


def reset_pipeline_run_context(token: Token[PipelineRunContext | None]) -> None:
    _current_run.reset(token)
