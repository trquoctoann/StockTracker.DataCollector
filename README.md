# StockTracker.DataCollector

Python 3.12 ingestion service using `vnstock==4.0.7`, pandas, FastAPI, and APScheduler. Listing/company payloads go to StockTracker.API over HTTP; candles/trades go through RabbitMQ. Optional PostgreSQL run tracking and an S3-compatible archive retain operational history.

Documentation was rebuilt from source at `c157150` on 2026-09-05. A completed collector job does not certify downstream persistence or complete exchange coverage.

| Document | Purpose |
| --- | --- |
| [Architecture](docs/architecture.md) | Pipelines, locking, run states, archive, scheduling |
| [Provider contract](docs/provider-contract.md) | Adapter operations, mapping, units and identity |
| [Operations](docs/operations.md) | Setup, triggers, resume and debugging |
| [Review](docs/review.md) | Defects and business gaps |
| [Agent instructions](AGENTS.md) | Collector-specific conventions |

```sh
uv sync --frozen --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/check_english_content.py
```

Run these in this repository's environment. The sibling [Deployment repository](../StockTracker.Deployment/README.md) owns containers and infrastructure. New company records currently encounter an [API response defect](../StockTracker.API/docs/review.md#a13).
