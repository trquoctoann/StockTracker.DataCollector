# DataCollector operations

## Configuration

`.env.example` is the complete local template. Major groups are API and Keycloak connectivity, RabbitMQ, control-plane PostgreSQL, raw archive, source selection, rate limits, market-data windows, scheduler timing, and in-memory job retention.

Use conservative source rates. The default vnstock rate is an application safety limit, not a provider quota guarantee. Do not add replicas to bypass provider limits.

## Database migration

The collector owns `collector.alembic_version` and all tables in the `collector` schema. Apply its migration before the API migration when upgrading an old shared local database:

```bash
uv run alembic current
uv run alembic upgrade head
```

The migration environment detects a complete legacy collector control plane that used `public.alembic_version`, stamps it into `collector.alembic_version`, and frees the public version table when it contains the collector revision. It does not stamp a partial schema.

## Service startup

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1
```

The lifespan initializes one shared HTTP client, Keycloak authentication, the optional control store, raw archive, job registry, and scheduler. AsyncExitStack closes resources on normal shutdown, startup failure, cancellation, or application failure.

## Run and inspect pipelines

Obtain a Keycloak client token with the `pipeline_operator` realm role, then call one of:

```text
POST /run/vnstock-listing
POST /run/vnstock-company
POST /run/vnstock-market-data
GET  /run/jobs/{job_id}
```

The POST endpoints return `202 Accepted` and a job ID. If the job is no longer retained in memory, the status endpoint falls back to the durable run record.

Resume a failed run by sending:

```json
{"resume_from": "00000000-0000-0000-0000-000000000000"}
```

Resume skips steps completed by the parent run. Sinks must remain idempotent because a process can stop after a sink commits but before the step status is persisted.

## Health checks

```bash
curl --fail http://localhost:8001/health/live
curl --fail http://localhost:8001/health/ready
curl --fail http://localhost:8001/metrics
```

Readiness reports `http_client=ok`, plus `control_database=ok` and `raw_archive=ok` when enabled. It intentionally does not call the public market source or Keycloak token endpoint, because an external provider incident must not cause a restart loop.

## Replay and recovery

`RawArchive.load(key, expected_checksum=...)` verifies SHA-256 before restoring JSON, pandas Series, or pandas table payloads. Replay is deliberate; no public endpoint automatically republishes archived data.

- Provider schema failure: preserve the raw object, update the compatibility contract and processor tests, then replay a known capture.
- API failure: keep the watermark unchanged and rerun or resume after API recovery.
- RabbitMQ failure: publishing fails and the run remains failed. There is no local spool, so replay the archived source response deliberately.
- Stale run: startup marks a run abandoned after `PIPELINE_STALE_AFTER_SECONDS` without a heartbeat.
- Raw archive failure: readiness fails and pipelines must not continue without the configured archive.

## Verification

```bash
uv run ruff check app tests scripts alembic
uv run ruff format --check app tests scripts alembic
uv run pyright
uv run pytest tests -q -p no:cacheprovider
uv lock --check
uv run python scripts/check_english_content.py
uvx --python .venv/bin/python pip-audit --path .venv/lib/python3.12/site-packages --skip-editable
uv run python scripts/smoke_vnstock.py --symbol FPT
```

The smoke command reads source data only. Run it for one symbol before enabling a broad schedule after an SDK update.
