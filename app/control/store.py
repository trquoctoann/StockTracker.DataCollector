from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from app.core.exceptions import PipelineBusyError

_LOG = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PipelineRunRecord:
    id: UUID
    pipeline: str
    status: str
    trigger: str
    submitted_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    finished_at: datetime | None
    error: str | None
    resume_of: UUID | None


@dataclass(frozen=True)
class WatermarkRecord:
    pipeline: str
    stream: str
    partition_key: str
    cursor: dict[str, Any]
    source: str | None
    run_id: UUID | None
    updated_at: datetime


class PipelineStore:
    """PostgreSQL-backed run state, watermarks and distributed locks."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5, command_timeout=30)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> None:
        pool = self._require_pool()
        await pool.fetchval("SELECT 1")

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PipelineStore is not connected")
        return self._pool

    @asynccontextmanager
    async def acquire_pipeline_lock(self, pipeline: str) -> AsyncIterator[None]:
        pool = self._require_pool()
        connection = await pool.acquire()
        lock_name = f"stocktracker:collector:{pipeline}"
        locked = False
        try:
            locked = bool(await connection.fetchval("SELECT pg_try_advisory_lock(hashtextextended($1, 0))", lock_name))
            if not locked:
                raise PipelineBusyError(f"Pipeline {pipeline} is already running in another collector")
            yield
        finally:
            if locked:
                try:
                    await connection.fetchval("SELECT pg_advisory_unlock(hashtextextended($1, 0))", lock_name)
                except Exception:
                    _LOG.exception("PIPELINE_ADVISORY_UNLOCK_FAILED", pipeline=pipeline)
            await pool.release(connection)

    async def start_run(
        self,
        run_id: UUID,
        pipeline: str,
        *,
        trigger: str,
        resume_of: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        pool = self._require_pool()
        now = datetime.now(UTC)
        await pool.execute(
            """
            INSERT INTO collector.pipeline_runs
                (id, pipeline, status, trigger, submitted_at, started_at, heartbeat_at, resume_of, metadata)
            VALUES ($1, $2, 'running', $3, $4, $4, $4, $5, $6::jsonb)
            """,
            run_id,
            pipeline,
            trigger,
            now,
            resume_of,
            json.dumps(dict(metadata or {})),
        )

    async def heartbeat(self, run_id: UUID) -> None:
        pool = self._require_pool()
        await pool.execute(
            "UPDATE collector.pipeline_runs SET heartbeat_at = now() WHERE id = $1 AND status = 'running'",
            run_id,
        )

    async def finish_run(self, run_id: UUID, status: str, *, error: str | None = None) -> None:
        if status not in {"completed", "failed", "cancelled", "abandoned"}:
            raise ValueError(f"Unsupported terminal pipeline status: {status}")
        pool = self._require_pool()
        await pool.execute(
            """
            UPDATE collector.pipeline_runs
            SET status = $2, error = $3, heartbeat_at = now(), finished_at = now()
            WHERE id = $1
            """,
            run_id,
            status,
            error,
        )

    async def recover_stale_runs(self, stale_after_seconds: int) -> int:
        pool = self._require_pool()
        result = await pool.execute(
            """
            UPDATE collector.pipeline_runs
            SET status = 'abandoned',
                error = 'collector stopped heartbeating before completion',
                finished_at = now()
            WHERE status = 'running'
              AND heartbeat_at < now() - ($1 * interval '1 second')
            """,
            stale_after_seconds,
        )
        return int(result.rsplit(" ", 1)[-1])

    async def get_run(self, run_id: UUID) -> PipelineRunRecord | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """
            SELECT id, pipeline, status, trigger, submitted_at, started_at,
                   heartbeat_at, finished_at, error, resume_of
            FROM collector.pipeline_runs WHERE id = $1
            """,
            run_id,
        )
        return PipelineRunRecord(**dict(row)) if row else None

    async def start_step(self, run_id: UUID, step_key: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        pool = self._require_pool()
        await pool.execute(
            """
            INSERT INTO collector.pipeline_steps
                (run_id, step_key, status, attempt, started_at, metadata)
            VALUES ($1, $2, 'running', 1, now(), $3::jsonb)
            ON CONFLICT (run_id, step_key) DO UPDATE
            SET status = 'running', attempt = collector.pipeline_steps.attempt + 1,
                started_at = now(), finished_at = NULL, error = NULL,
                metadata = collector.pipeline_steps.metadata || EXCLUDED.metadata
            """,
            run_id,
            step_key,
            json.dumps(dict(metadata or {})),
        )

    async def finish_step(self, run_id: UUID, step_key: str, status: str, *, error: str | None = None) -> None:
        if status not in {"completed", "failed", "skipped"}:
            raise ValueError(f"Unsupported terminal step status: {status}")
        pool = self._require_pool()
        await pool.execute(
            """
            UPDATE collector.pipeline_steps
            SET status = $3, error = $4, finished_at = now()
            WHERE run_id = $1 AND step_key = $2
            """,
            run_id,
            step_key,
            status,
            error,
        )

    async def completed_steps(self, run_id: UUID) -> set[str]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT step_key FROM collector.pipeline_steps WHERE run_id = $1 AND status = 'completed'",
            run_id,
        )
        return {str(row["step_key"]) for row in rows}

    async def put_watermark(
        self,
        pipeline: str,
        stream: str,
        partition_key: str,
        cursor: Mapping[str, Any],
        *,
        source: str | None,
        run_id: UUID | None,
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """
            INSERT INTO collector.watermarks
                (pipeline, stream, partition_key, cursor, source, run_id, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, now())
            ON CONFLICT (pipeline, stream, partition_key) DO UPDATE
            SET cursor = EXCLUDED.cursor, source = EXCLUDED.source,
                run_id = EXCLUDED.run_id, updated_at = now()
            """,
            pipeline,
            stream,
            partition_key,
            json.dumps(dict(cursor)),
            source,
            run_id,
        )

    async def get_watermark(self, pipeline: str, stream: str, partition_key: str) -> WatermarkRecord | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """
            SELECT pipeline, stream, partition_key, cursor, source, run_id, updated_at
            FROM collector.watermarks
            WHERE pipeline = $1 AND stream = $2 AND partition_key = $3
            """,
            pipeline,
            stream,
            partition_key,
        )
        if row is None:
            return None
        values = dict(row)
        cursor = values["cursor"]
        if isinstance(cursor, str):
            values["cursor"] = json.loads(cursor)
        return WatermarkRecord(**values)

    async def record_raw_object(
        self,
        *,
        run_id: UUID,
        pipeline: str,
        operation: str,
        object_key: str,
        checksum_sha256: str,
        row_count: int | None,
        source: str | None,
        schema_version: str,
        parameters: Mapping[str, Any],
    ) -> None:
        pool = self._require_pool()
        await pool.execute(
            """
            INSERT INTO collector.raw_objects
                (run_id, pipeline, operation, object_key, checksum_sha256,
                 row_count, source, schema_version, parameters)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (object_key) DO NOTHING
            """,
            run_id,
            pipeline,
            operation,
            object_key,
            checksum_sha256,
            row_count,
            source,
            schema_version,
            json.dumps(dict(parameters)),
        )
