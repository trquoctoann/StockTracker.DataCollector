# Collector review

Reviewed 2026-09-05 against `c157150`. Findings remain open. P1/P2/P3 priorities follow the [cross-repository review](../../StockTracker.Deployment/docs/review.md). Validation: 141 tests passed; Ruff lint/format and Pyright passed. Local probes used processors, in-memory S3 objects, and metrics. The follow-up Docker review used real PostgreSQL, S3Mock, RabbitMQ and bounded vnstock calls. See [runtime evidence](../../StockTracker.Deployment/docs/runtime-validation.md). C02/C03 were reproduced with live storage; C01 downstream persistence required a labeled test-only workaround for API A17. C05 used controlled heartbeat aging, not a full process-crash drill.

<a id="c01"></a>
## C01 [P2] Repeated trade identities can poison a whole upsert batch

Source: [app/plugins/processors/market_data_processor.py:98](../app/plugins/processors/market_data_processor.py#L98), [app/plugins/processors/pandas_utils.py:87](../app/plugins/processors/pandas_utils.py#L87), [app/plugins/sources/vnstock_source.py:297](../app/plugins/sources/vnstock_source.py#L297).

Evidence: Two trade rows without provider IDs and with equal timestamp/price/volume/side produce the same data_source_id; reproduced with the real processor. Concatenated pages are not deduplicated. API passes all records into one PostgreSQL ON CONFLICT DO UPDATE statement.

Live validation: After bypassing the separate API enum-schema blocker only in the disposable fixture, a synthetic duplicate-key trade batch inserted zero rows and reached DLQ after three retries. This verifies the receiver failure; it does not establish whether two equal provider trades are semantically duplicates.

Impact: Repeated natural keys in one statement cause a PostgreSQL cardinality error, so the entire chunk retries and can end in DLQ. If equal-field rows were actually distinct trades, the fallback cannot preserve their identity even across separate batches.

Recommended correction: Preserve a stable provider trade ID when available. Define duplicate delivery versus distinct-trade semantics, deduplicate proven delivery duplicates before batch upsert, and reject ambiguous identity instead of claiming full trade fidelity.

Regression criterion: Cover overlapping pages, repeated delivery rows, distinct trades at the same timestamp, and repeated keys in a real PostgreSQL batch.

<a id="c02"></a>
## C02 [P2] Raw load loses DataFrame source context needed for equivalent replay

Source: [app/archive/raw_archive.py:71](../app/archive/raw_archive.py#L71), [app/archive/raw_archive.py:241](../app/archive/raw_archive.py#L241), [app/plugins/processors/company_processor.py:61](../app/plugins/processors/company_processor.py#L61).

Evidence: Local capture/load of a KBS shareholder DataFrame returns attrs={}. Passing the result to the real processor changes the ID prefix from kbs:shareholder to vnstock:shareholder. The envelope retains source separately, but load does not apply it to the reconstructed frame.

Live validation: Real S3Mock capture/load preserved DataFrame values and separate source=KBS metadata, but loaded DataFrame.attrs was empty. Incorrect checksums were rejected.

Impact: Direct replay is not equivalent to the original transformation. KBS profile fields deliberately omitted by source-aware logic can also bypass that branch after load. There is no integrated replay pipeline compensating for this.

Recommended correction: Restore required source/normalization metadata in reconstructed payloads or make processors accept it explicitly through a maintained replay adapter. Preserve schema version and verify checksums in that workflow.

Regression criterion: Capture/load/transform the same KBS profile and company collection; assert identical canonical payloads, IDs and unit-related field omissions.

<a id="c03"></a>
## C03 [P2] A second resume reruns steps that were skipped on the first resume

Source: [app/engine/pipeline.py:95](../app/engine/pipeline.py#L95), [app/engine/pipeline.py:162](../app/engine/pipeline.py#L162), [app/control/store.py:198](../app/control/store.py#L198).

Evidence: Run A completes X and fails Y. Run B resumes A, writes X as skipped, and fails Y again. Run C resumes B; completed_steps(B) excludes skipped X, so X runs again. This follows the actual step state/query logic; current tests cover only one parent resume.

Live validation: With the real PipelineStore, three attempts ended failed/failed/completed. The first step executed on attempts 0 and 2, reproducing inherited-checkpoint loss.

Impact: Repeated recovery re-fetches and re-delivers work already known complete, increasing provider calls and potentially changing replacement snapshots or rolling windows.

Recommended correction: Carry inherited completion forward or resolve successful steps across the resume ancestry, with explicit run-configuration compatibility rules.

Regression criterion: Exercise A -> B -> C where the same later step fails twice. The original successful step must remain skipped and not call the provider/sink again.

<a id="c04"></a>
## C04 [P2] Freshness metrics disappear on restart or before any success

Source: [app/middleware/metrics.py:17](../app/middleware/metrics.py#L17), [app/middleware/metrics.py:31](../app/middleware/metrics.py#L31).

Evidence: The last-success map exists only in memory and only gets entries on completion. A local first-failure probe emits no last-success sample. Deployment stale alert compares time() with that series but has no missing-series branch.

Live validation: The collector HTTP process exposed no last-success samples and the live Prometheus stale expression returned an empty vector before any successful HTTP-process pipeline run.

Impact: A never-successful or restarted pipeline can remain absent from stale alert evaluation. The normal failure alert does not replace a durable no-success signal, particularly for pipelines that never ran.

Recommended correction: Export known pipeline freshness from durable state or initialize expected series with explicit never-succeeded semantics. Add absent/never-started handling and define disabled-scheduler behavior.

Regression criterion: Verify alert behavior with no runs, first failure, successful run, and process restart; distinguish disabled scheduling from missed expected execution.

<a id="c05"></a>
## C05 [P2] Quick restart can strand interrupted runs in running status

Source: [app/main.py:121](../app/main.py#L121), [app/control/store.py:144](../app/control/store.py#L144), [app/main.py:293](../app/main.py#L293).

Evidence: Stale recovery executes once at startup. If a process restarts before the stale threshold, its interrupted running record is too recent to be marked abandoned. It later becomes old but no periodic recovery revisits it.

Live validation: A real store row was not recovered before the threshold; after direct SQL heartbeat aging it remained running until explicit recovery marked it abandoned. This is a store-boundary reproduction, not a timed process-restart drill.

Impact: The run stays running indefinitely and resume rejects it, even though the old process is gone and the advisory lock is released.

Recommended correction: Add lease/lock-aware periodic recovery or validate recoverability at resume time. Avoid abandoning a live run solely because it has temporarily missed a heartbeat.

Regression criterion: Terminate an active collector and restart before the threshold. After the threshold the interrupted run must become recoverable without another restart, while live runs remain protected.

## Cross-repository blockers and unresolved business behavior

- API A13 causes new company rows to fail their response after persistence; the collector's lack of HTTP-status retries exposes this as failed steps. Fix the API contract, rather than retrying all 500 responses blindly.
- Market step completion means broker publication, not canonical persistence. No run ID is carried in the message and no consumer result reconciles the run state.
- Default intraday sampling is one page of 100 rows once per scheduled day. Full-day collection, market calendars and retention are not implemented.
- Watermarks are written but do not drive history fetch windows. Resuming later uses new rolling dates/settings.
- HTTP retry covers network failures, not 429/5xx; token refresh is time-based and does not react to a rejected cached token. Decide transient-status policy before advertising resilient retries.
- Schedules do not wait for each other and per-process rate limits are not shared across replicas. PostgreSQL locks only serialize the same pipeline name.
- Empty company snapshots are always rejected; legitimate deletion-to-empty requires an explicit authoritative signal. No automatic raw replay or cancellation endpoint exists.
- Accepted pending jobs are in memory until engine start, and runs failing before durable start can be lost from history on restart. JOB_HISTORY_LIMIT limits memory, not database/archive retention.
- Provider prices/percentages, corporate-action adjustments, KBS omitted fields and complete index coverage require product/source evidence. They are not assumed correct merely because schemas parse.
