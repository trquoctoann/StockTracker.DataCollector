from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
VERSION_TABLE_SCHEMA = "collector"
CONTROL_PLANE_REVISION = "202608300001"
CONTROL_PLANE_TABLES = (
    "collector.pipeline_runs",
    "collector.pipeline_steps",
    "collector.watermarks",
    "collector.raw_objects",
)
config.set_main_option(
    "sqlalchemy.url", settings.control_database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    context.execute(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}")
    with context.begin_transaction():
        context.run_migrations()


def _prepare_version_table(connection) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}"))
    collector_version_table = connection.scalar(text("SELECT to_regclass('collector.alembic_version')"))
    control_plane_exists = all(
        connection.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}) is not None
        for table_name in CONTROL_PLANE_TABLES
    )
    if collector_version_table is None and control_plane_exists:
        connection.execute(
            text(
                """
                CREATE TABLE collector.alembic_version (
                    version_num varchar(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                )
                """
            )
        )
        connection.execute(
            text("INSERT INTO collector.alembic_version (version_num) VALUES (:revision)"),
            {"revision": CONTROL_PLANE_REVISION},
        )
        public_version_table = connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
        if public_version_table is not None:
            public_revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            if public_revision == CONTROL_PLANE_REVISION:
                connection.execute(text("DELETE FROM public.alembic_version"))


def do_run_migrations(connection) -> None:
    _prepare_version_table(connection)
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(config.get_main_option("sqlalchemy.url"), pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
