# Provider and delivery contract

This describes the checked-in adapter for vnstock 4.0.7. Five bounded provider operations succeeded in the Docker review on 2026-09-05: industry/stock catalogs, FPT overview, five FPT history candles and one 100-row FPT trade page. See [captured runtime evidence](../../StockTracker.Deployment/docs/runtime-validation.md#collector-state-archive-and-provider). This establishes sampled compatibility, not future availability, complete coverage or financial units. Representative fixtures and source code define the implemented mapping.

## Adapter operations

| Operation | Unified UI call | Source |
| --- | --- | --- |
| industries_icb | `Reference().industry.list` | VCI fixed |
| symbols_by_exchange | `Reference().equity.list_by_exchange` | KBS default; VCI selectable |
| symbols_by_group | `Reference().equity.list_by_group` | KBS |
| indices_catalog | INDEX_GROUPS/INDICES_INFO plus `Reference().index.groups` and equity memberships | KBS supported groups |
| company_overview | `Reference().company(symbol).info` | KBS default; VCI selectable |
| company_shareholders/officers/subsidiaries/events/news | Matching company method | KBS default; VCI selectable |
| quote_history | `Market().equity(symbol).ohlcv` | KBS default; VCI selectable |
| quote_intraday | `Market().equity(symbol).trades` | KBS default; VCI selectable |

All provider imports/construction happen inside worker-thread calls. Before import, both VNSTOCK_DISABLE_AGENT_SETUP and VNSTOCK_DISABLE_GLOBAL_AGENT are set to 1 to stop the SDK from modifying agent configuration. SystemExit becomes SourceError inside the worker; cancellation/KeyboardInterrupt are not converted into successful extraction.

## Listing normalization

Industry rows use icb_code/icb_name/level. Stock input requires symbol/organ_name/exchange/type. Allowed collected types are STOCK, ETF, UNIT_TRUST and FUND. UNIT_TRUST becomes FUND, and HOSE becomes HSX. Symbol strings are stripped/uppercased. Unsupported asset types are filtered out.

Only a resolvable icb_code2 produces an industry ID. Missing industry evidence leaves industry_ids unset, preserving API links. KBS sector classifications are not treated as ICB codes. The pipeline does not establish complete multi-level industry membership.

Index aliases are VNMID -> VNMidCap, VNSML -> VNSmallCap, VNINDEX -> HOSE for provider lookup. Requested groups are intersected with provider-supported groups; unsupported symbols are logged/skipped. Included baskets must have nonempty constituent symbols and every symbol must map to an API stock ID. Default requests include configured HOSE/Sector/Investment/VNX groups and extra HNX30; this does not guarantee each requested group is returned.

## Company normalization

Profile aliases include listed_volume -> listing_volume, num_employees -> number_of_employees, company_profile -> business_model. For KBS, charter_capital and listing_volume are deliberately omitted because the adapter does not establish their canonical unit scaling. No guessed multiplier should be introduced.

Shareholder aliases include share_holder/name, shares_owned/quantity, ownership_percentage or share_own_percent/ownership_percent, and update_date/updated_date. Officer aliases include officer_name, officer_position, officer_own_percent and officer_own_quantity. Affiliations use organ_name/name and sub_organ_code/code, with selected provider type labels mapped to canonical strings. Events/news normalize title/date/source URL aliases.

REST serialization uses exclude_none=True. Omitted provider values therefore do not request explicit null updates. Snapshot collections must retain every input row and be nonempty before the company pipeline sends them. The API distinguishes replacement-style shareholder/officer/affiliate collections from append/update event/news history.

record_id preserves explicit data_source_id; otherwise it prefixes a provider-supplied ID or hashes selected identity fields. Mutable quantity/ownership/update date is excluded from company identities. Hashing name/position is still not a verified global identity for a person, and provider changes can change IDs. Source attrs are required for provider-specific handling; archive replay currently loses them [C02](review.md#c02).

## Market normalization

History requires time/open/high/low/close/volume. Trade input requires time/price/volume. Nonfinite, negative, or unparseable numbers are rejected by the market processor. Timestamp strings must begin with an ISO date, and parsed timestamps must be at least year 1900.

Timezone-aware values become naive Asia/Ho_Chi_Minh times. Day/week/month candles become midnight on the local date; smaller intervals retain their timestamp. VCI receives `1H` for API interval `1h`. No price-unit scaling or corporate-action adjustment is performed in this processor.

B/BUY -> BUY; S/SELL -> SELL; unsupported/auction sides -> null. Trade fallback IDs hash timestamp, price, volume and side. This can give multiple rows the same natural key [C01](review.md#c01).

History fetches use configured start/end or a rolling 30-calendar-day lookback ending today in Vietnam. No stored watermark drives the next fetch. Intraday loops page 1 through max_pages, stopping on empty/short pages. Defaults are 100 records/page and one page. Reaching the cap logs VNSTOCK_INTRADAY_WINDOW_LIMIT but still succeeds. It is recent-window sampling, not complete intraday history.

Market output uses JSON objects with stock_id/records and candle interval, with stock_id also in each record. See the API's [message contracts](../../StockTracker.API/docs/contracts.md). Default chunks contain up to 500 records. RabbitMQ publication is persistent and uses confirms plus returned-message errors; database persistence is a separate stage.

## Required business decisions

The code does not establish currency/price units across providers, percentage scale for every source, adjusted versus unadjusted candle policy, trading calendar, complete intraday retention, full index coverage, or a reliable empty-snapshot clearing signal. These must be decided from product requirements and real provider evidence, then encoded in validation and fixtures. Documentation must not silently fill them in.
