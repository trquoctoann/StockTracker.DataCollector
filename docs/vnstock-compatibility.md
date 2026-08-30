# vnstock 4.0.7 compatibility contract

Last reviewed: 2026-08-30. Package: public `vnstock==4.0.7`, not the sponsored `vnstock_data` package. The dependency is pinned because provider methods, schemas, and supported capabilities have changed between releases.

## Verified calls

| Collector operation | SDK call | Default source |
|---|---|---|
| ICB industries | `Reference().industry.list(source="vci")` | VCI |
| Exchange symbols | `Reference().equity.list_by_exchange(source=...)` | KBS |
| Index members | `Reference().equity.list_by_group(group=..., source="kbs")` | KBS |
| Company profile | `Reference().company(symbol).info(source=...)` | KBS |
| Shareholders, officers, subsidiaries, events, news | Matching method on `Reference().company(symbol)` | KBS |
| Price history | `Market().equity(symbol).ohlcv(start=..., end=..., interval=..., count=None, source=...)` | KBS |
| Intraday trades | `Market().equity(symbol).trades(page=..., page_size=..., source=...)` | KBS |

Index capability is discovered from `Reference().index.groups(source="kbs")`. Metadata-only groups are excluded when the provider does not expose membership. VNMID and VNSML use the aliases accepted by `equity.list_by_group`.

## Source and schema rules

- KBS listing data does not provide ICB classification. The collector omits `industry_ids` rather than sending an empty destructive snapshot.
- Company aliases differ between KBS and VCI. Processors map observed field names and reject missing required columns.
- Stable provider-prefixed IDs are preferred. Deterministic hashes are used only when the provider has no ID.
- KBS charter capital and listed volume are omitted until their display units can be proven against a canonical source.
- Empty company operations do not delete existing API records.
- Company events and news may expose only a recent window. The API retains history through append/upsert behavior.
- The default price-history window is 30 days. Durable watermarks advance after successful sinks and override the fallback window where available.
- Daily period timestamps are normalized to local midnight. The database currently stores naive local timestamps.
- Intraday defaults to one page of 100 rows and does not claim full-session coverage.
- ATO, ATC, and unknown trade sides map to null because the API enum contains only BUY and SELL.

## SDK execution limits

The SDK is imported and called in a worker thread so startup and health endpoints do not depend on source import behavior. `SystemExit` is converted to a source error. Async cancellation is preserved, but Python cannot forcibly stop a synchronous SDK thread that is already running.

Before every SDK import, the adapter forces `VNSTOCK_DISABLE_AGENT_SETUP=1` and `VNSTOCK_DISABLE_GLOBAL_AGENT=1`. This prevents the provider package from creating or modifying project and user-level AI agent configuration files from a data-service process.

## Upgrade procedure

1. Read the package release notes and inspect the installed wheel API.
2. Update the exact version and lockfile in one commit.
3. Run unit, contract, static, and dependency-audit checks.
4. Run the source-only smoke for FPT and explicitly selected operations.
5. Compare columns, units, row counts, provider IDs, timestamps, and empty-result behavior.
6. Run the Docker data-foundation E2E against a clean database.
7. Update this document with changed methods, mappings, limitations, and verification evidence.
8. Deploy with the scheduler disabled, run one controlled pipeline, inspect archived raw data and normalized records, then enable the intended schedule.

## Known limitations

Provider availability and schemas can change independently of the Python package. KBS events returned an empty frame for FPT during the last review, so a non-empty event contract is not yet proven. Intraday pagination can shift while the market is open. No source call is treated as authoritative enough to erase a prior snapshot unless completeness is explicitly established.

Primary references: [vnstock PyPI 4.0.7](https://pypi.org/project/vnstock/4.0.7/), [official repository](https://github.com/thinh-vu/vnstock), and [vnstock package documentation](https://vnstocks.com/docs/vnstock).
