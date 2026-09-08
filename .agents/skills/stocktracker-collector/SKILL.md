---
name: stocktracker-collector
description: Change StockTracker.DataCollector provider adapters, transformations, pipeline execution, message delivery and control-plane persistence while preserving source and API contracts.
---

# StockTracker collector development

Read [AGENTS.md](../../../AGENTS.md), [provider contract](../../../docs/provider-contract.md), [architecture](../../../docs/architecture.md) and relevant [findings](../../../docs/review.md). Work in this repository's Python environment; the API package name collides with this application's package.

## Trace one operation end to end

Identify source operation -> provider/source choice -> raw capture -> normalized schema -> sink endpoint/routing key -> checkpoint/watermark. Inspect the API receiver when changing a payload. Keep SDK calls in VnstockSource and blocking imports/calls in the worker thread with both agent-setup-disable flags. Do not move provider initialization into startup or test collection.

For mappings, use raw representative fixtures and explicit field/unit evidence. Preserve KBS/VCI distinctions, ICB meaning, HOSE-to-HSX and UNIT_TRUST-to-FUND normalization, local-time handling, and lowercase 1h on the API boundary. Unknown values must not become plausible invented values. Company REST payloads use items; market messages use records.

Determine delivery semantics before coding: complete replacement snapshot, patch/upsert, or recent-window sample. An empty/partial response is not authority to delete existing data. Null omission preserves stored values. Verify stable identity across repeats, provider changes, page overlap and archive load; do not infer unique trades from equal price/volume/time alone.

## Operational changes

Use existing pipeline dependency dataclasses and shared HTTP/rate-limiter/auth objects. Preserve run-scoped context and stable checkpoint keys. Resume re-fetches source data with current configuration; raw replay reconstructs archived inputs and needs source/schema metadata. Test repeated resume through at least two failures when changing inherited checkpoints.

Keep collector SQL in its own schema/history. Check advisory lock ownership, lease recovery after quick restart, heartbeat failure and cancellation. Do not call a step persisted merely because RabbitMQ confirmed publication. If adding completion reconciliation, carry run/correlation identity through producer and consumer together.

Expose intended settings through Settings, example env and Deployment mapping. Retry only declared transient outcomes with bounded attempts; test uncertain delivery and idempotency. A live provider call is not required for every code change; deterministic fixtures plus explicit live-smoke limitations are valid evidence.

Run the AGENTS.md checks and relevant contract/state-transition tests. Update documentation and close findings only after their regression criteria hold.

## Runtime review fixtures

The completed Docker review demonstrated open defects using temporary admin bootstrap, Keycloak scope/admin setup and market enum DDL in disposable containers. The temporary scripts were removed; the final report records these fixture limitations. Never copy those fixture changes into production or call downstream fixture-assisted success a passing baseline regression. For a fix, rerun the affected flow from checked-in migrations/imports without its workaround. Python Enum fields must agree with real PostgreSQL types and stored labels; successful Alembic upgrade alone does not prove that agreement.
