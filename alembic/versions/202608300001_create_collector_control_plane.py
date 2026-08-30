"""create collector control plane

Revision ID: 202608300001
Revises:
"""

from alembic import op

revision = "202608300001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS collector")
    op.execute(
        """
        CREATE TABLE collector.pipeline_runs (
            id uuid PRIMARY KEY,
            pipeline varchar(120) NOT NULL,
            status varchar(20) NOT NULL,
            trigger varchar(30) NOT NULL,
            submitted_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            heartbeat_at timestamptz,
            finished_at timestamptz,
            error text,
            resume_of uuid REFERENCES collector.pipeline_runs(id),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_pipeline_run_status CHECK (
                status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'abandoned')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_pipeline_runs_pipeline_started ON collector.pipeline_runs (pipeline, started_at DESC)")
    op.execute("CREATE INDEX ix_pipeline_runs_status_heartbeat ON collector.pipeline_runs (status, heartbeat_at)")
    op.execute(
        """
        CREATE TABLE collector.pipeline_steps (
            id bigserial PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES collector.pipeline_runs(id) ON DELETE CASCADE,
            step_key varchar(300) NOT NULL,
            status varchar(20) NOT NULL,
            attempt integer NOT NULL DEFAULT 1,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            error text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_pipeline_step UNIQUE (run_id, step_key),
            CONSTRAINT ck_pipeline_step_status CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
            CONSTRAINT ck_pipeline_step_attempt CHECK (attempt > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE collector.watermarks (
            pipeline varchar(120) NOT NULL,
            stream varchar(120) NOT NULL,
            partition_key varchar(300) NOT NULL,
            cursor jsonb NOT NULL,
            source varchar(80),
            run_id uuid REFERENCES collector.pipeline_runs(id) ON DELETE SET NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (pipeline, stream, partition_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE collector.raw_objects (
            id bigserial PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES collector.pipeline_runs(id) ON DELETE CASCADE,
            pipeline varchar(120) NOT NULL,
            operation varchar(120) NOT NULL,
            object_key text NOT NULL UNIQUE,
            checksum_sha256 char(64) NOT NULL,
            row_count integer,
            source varchar(80),
            schema_version varchar(40) NOT NULL,
            parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_raw_object_row_count CHECK (row_count IS NULL OR row_count >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_raw_objects_run_operation ON collector.raw_objects (run_id, operation)")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS collector CASCADE")
