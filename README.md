# StockTracker DataCollector

DataCollector extracts Vietnamese market data through the pinned vnstock SDK, validates and transforms provider responses, archives raw payloads, and sends normalized data to StockTracker API or RabbitMQ. It also owns durable pipeline control metadata in the PostgreSQL `collector` schema.

## Quick start

```powershell
uv sync --frozen --dev
uv run alembic upgrade head
uv run pytest -q -p no:cacheprovider
uv run ruff check app tests scripts
uv run pyright
uv run python scripts/smoke_vnstock.py --symbol FPT
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Copy `.env.example` to `.env` and configure the Keycloak machine client before running a write pipeline. The source smoke test reads and transforms provider data but does not call the API or broker. `/run/*` and `/run/jobs/*` require a Bearer token with the `pipeline_operator` realm role.

When the control plane is enabled, the collector records runs, steps, heartbeats, watermarks, and raw object manifests. Raw responses are compressed, checksummed, and stored in S3 or S3Mock before transformation. A failed run can resume completed steps with `{"resume_from":"<run-id>"}`.

## Documentation

- [Architecture](docs/architecture.md)
- [Operations and recovery](docs/operations.md)
- [vnstock 4.0.7 compatibility contract](docs/vnstock-compatibility.md)
- [Contribution and documentation rules](CONTRIBUTING.md)
