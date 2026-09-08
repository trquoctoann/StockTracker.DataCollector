# Collector agent instructions

For collector changes, read [.agents/skills/stocktracker-collector/SKILL.md](.agents/skills/stocktracker-collector/SKILL.md), [architecture](docs/architecture.md), [provider contract](docs/provider-contract.md) and relevant [findings](docs/review.md).

## Conventions

- Python 3.12; own virtual environment and cwd. Install with `uv sync --frozen --dev`. API uses the same package name `app`; do not import it in-process to share runtime contracts. Use isolated contract tests/fixtures instead.
- Follow pyproject.toml: Ruff 120-column/double-quote formatting, configured imports/rules and Pyright basic. Use snake_case modules/functions, PascalCase classes, typed boundaries and uppercase structured log events. Keep dependencies pinned by uv.lock; vnstock is exactly 4.0.7 until a deliberate compatibility change.
- Provider-specific SDK calls belong in VnstockSource. Preserve lazy import, worker-thread execution and both VNSTOCK_DISABLE_* agent-setup flags. Tests, health and startup must not import/contact the provider unnecessarily. Convert SDK SystemExit inside the thread; preserve cancellation.
- Processors perform normalization; schemas define payloads; sinks perform transport; pipelines orchestrate. Inject settings/rate limiter/auth/HTTP/archive dependencies using existing dependency dataclasses. Do not introduce direct canonical-database writes.
- Keep provider evidence: unknown units stay unknown; KBS sectors are not ICB. Do not fill unknown trade side with BUY/SELL. Preserve local market time normalization and exact interval case. Distinguish missing values from zero and explicit deletion.
- Prefer stable source IDs and deterministic replay. Do not include mutable quantities in company identity. Deduplicate only where duplicate semantics are established; do not collapse distinct trades by convenience.
- Company snapshot safety requires validated, nonempty and complete rows before replacement delivery. Events/news and replacement snapshots have different API semantics. Preserve exclude_none serialization and exact items/records envelope shapes.
- Use PipelineEngine.run/step and stable step keys. Keep local/distributed exclusion, heartbeats and cancellation cleanup. Do not equate publisher success or an observation watermark with database persistence. Repeated resume and raw replay are distinct workflows.
- Add control-schema changes through collector Alembic history and collector.alembic_version. API migrations/default schema belong to the sibling repository. Archive writes need active run context and schema/source metadata.
- Update Settings, .env.example and Deployment environment mapping together for settings intended to be operationally configurable. Cron, retry and rate-limit behavior must be stated accurately.
- Maintained text is English ASCII. Use explicit Unicode escapes for necessary provider fixtures. Log symbols, run IDs, steps and counts; never tokens/client secrets or full secret-bearing configuration.

## Verification

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/check_english_content.py
uv run pytest -q
```

Use fixtures to test actual provider column shapes, timestamps, IDs, enums, missing fields and bad values. For contract changes, validate serialized output against API inputs in separate processes. For replay/resume changes, test multi-stage failures and metadata preservation. Live vnstock smoke is separate from ordinary tests and requires a deliberate provider-call budget/environment.

State when real PostgreSQL, RabbitMQ, S3 or provider checks could not run. Update docs/findings to reflect demonstrated behavior, not expected behavior. Avoid speculative refactors outside the requested change.
