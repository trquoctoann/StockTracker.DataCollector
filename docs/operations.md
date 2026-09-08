# Collector operations

Run commands in StockTracker.DataCollector with its own Python 3.12 environment.

```sh
uv sync --frozen --dev
```

Copy `.env.example` to `.env` only when absent, then configure target addresses and credentials. Settings accept case-insensitive environment names and ignore unknown dotenv fields. Host defaults use API port 5000; the supplied Compose stack exposes API at 8000. Configure STOCKTRACKER_API_BASE_URL for the actual target.

## Configuration

The complete authoritative definitions are [Settings](../app/core/config.py). Standalone defaults and Deployment overrides differ.

| Group | Key fields/defaults |
| --- | --- |
| API | STOCKTRACKER_API_BASE_URL; API_PATH_* for lookup/sync routes |
| Keycloak | KEYCLOAK_BASE_URL, REALM, CLIENT_ID (data-collector-service), CLIENT_SECRET; token skew 30 seconds |
| HTTP | HTTP_TIMEOUT_SECONDS=60; rate 10/second, burst 20 |
| RabbitMQ | RABBITMQ_ENABLED=false; URL, EXCHANGE, EXCHANGE_TYPE; routing keys stock_price_history.sync and stock_intraday.sync; rate 50/second, burst 100 |
| Control plane | CONTROL_PLANE_ENABLED=false; CONTROL_DATABASE_URL; heartbeat 30s, stale threshold 300s, JOB_HISTORY_LIMIT=1000 |
| Raw archive | RAW_ARCHIVE_ENABLED=false; ENDPOINT_URL, ACCESS_KEY, SECRET_KEY, REGION, BUCKET, PREFIX, SCHEMA_VERSION under RAW_ARCHIVE_ |
| Provider | VNSTOCK_LISTING_SOURCE/COMPANY_SOURCE/QUOTE_SOURCE=KBS; INDICES_SOURCE=KBS only; vnstock rate 0.25/second, burst 1 |
| History | VNSTOCK_PRICE_HISTORY_INTERVAL=1D; optional HISTORY_START/HISTORY_END; HISTORY_LOOKBACK_DAYS=30 |
| Trades | VNSTOCK_INTRADAY_PAGE_SIZE=100; VNSTOCK_INTRADAY_MAX_PAGES=1 |
| Batching | MARKET_DATA_CHUNK_SIZE=500 |
| Cron | SCHEDULER_ENABLED=false; SCHEDULER_TIMEZONE=Asia/Ho_Chi_Minh; listing 06:00, company 07:00, market 18:00 |

RAW_ARCHIVE_ENABLED requires access/secret keys. An absent endpoint selects normal S3 rather than S3Mock. Start must not exceed end. Not every setting is forwarded by the current Compose manifest; see [Deployment D05](../../StockTracker.Deployment/docs/review.md#d05).

When using durable control state, apply its migrations to the intended database before starting:

```sh
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Latest reviewed collector revision: `202608300001`. Its version table is collector.alembic_version. Do not stamp API migrations with collector revisions. Collector downgrade currently drops the collector schema with CASCADE and should be treated as data destruction.

## Trigger and inspect

Obtain a Keycloak bearer token with realm role pipeline_operator. Collector introspects it with its configured client, checks active=true and the role. The collector's own M2M token uses data_ingest for API delivery. Token acquisition is a separate operation; no token or secret belongs in documentation.

| Method/path | Purpose |
| --- | --- |
| POST `/run/vnstock-listing` | Submit listing pipeline |
| POST `/run/vnstock-company` | Submit company pipeline |
| POST `/run/vnstock-market-data` | Submit market pipeline; broker required |
| GET `/run/jobs/{job_id}` | Read registry/durable job status |

Each POST returns 202 with job_id/pipeline/status. Poll the job resource with the same operator authorization. A 202 response is acceptance, not completion. Same-process overlap produces 409; distributed lock contention can instead appear as a failed accepted job.

For resume, POST to the same pipeline endpoint with:

```json
{"resume_from":"00000000-0000-0000-0000-000000000001"}
```

Use a real failed/cancelled/abandoned run ID. Missing history gives 404, mismatched pipeline or status gives 409, and disabled durable storage gives 503. Resume creates a new run and reuses completed-step knowledge with the [C03 limitation](review.md#c03). There is no automatic restart-resume or HTTP cancel/replay endpoint.

## Health and diagnosis

Liveness checks the HTTP process. Readiness checks HTTP client initialization and, if enabled, control database ping and archive bucket access. It does not call vnstock, obtain a token, verify API schema/data, or prove RabbitMQ consumption.

Inspect run/step errors and worker logs as well as HTTP readiness. Market job success proves publication only. For truncated trades, look for VNSTOCK_INTRADAY_WINDOW_LIMIT. For company failures, distinguish rejected empty/incomplete provider snapshots from API response errors [A13](../../StockTracker.API/docs/review.md#a13).

Stale-run recovery happens only during startup; a quick restart can leave interrupted runs stuck [C05](review.md#c05). Do not change rows from running to abandoned without checking that no collector owns the pipeline lock. Archive load is a library operation and does not itself replay ingestion.

## Validation

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/check_english_content.py
uv run pytest -q
```

On 2026-09-05, 141 existing tests plus Ruff/Pyright passed. Tests use provider/transport/storage fakes. The follow-up Docker review used real PostgreSQL, S3Mock, broker/API diagnostics and five bounded vnstock operations. See [runtime validation](../../StockTracker.Deployment/docs/runtime-validation.md). The separate scripts/smoke_vnstock.py was not invoked; the review's bounded provider harness was used instead. Neither establishes full-market completeness.

## Docker review and known startup blockers

See [runtime validation](../../StockTracker.Deployment/docs/runtime-validation.md) for the final diagnostic observations. Fresh migrations currently disagree with API market enum models (A17); human identity tokens and identity-administration configuration have separate blockers (D06/D07). The review used temporary bootstrap, scope/admin and enum fixtures. These are documented evidence limitations, not supported deployment steps or production fixes; the temporary harness was removed after the review.
