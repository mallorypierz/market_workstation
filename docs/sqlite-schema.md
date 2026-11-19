# Observation recorder schema and identity

Implemented with Python sqlite3, no added packages. Default path: `backend/data/market.sqlite3` under the project root. `MARKET_DB_PATH` overrides it; relative environment paths resolve against the root. Runtime SQLite files and sidecars are already excluded by `.gitignore`.

## Tables

- `observations`: integer observation_id; source namespace; ticker; source_time_json preserving the original type/value (or JSON null); optional source_time_ms integer interpreted using the investigated Yahoo millisecond convention; canonical payload_json containing every decoded source field. Unique constraint on `(source, payload_json)`.
- `deliveries`: autoincrement receipt_id; observation_id foreign key; UTC callback receipt_time; decoded_message_json retaining all received decoded fields for that delivery. Every arrival, including an exact repeat, gets a row.
- `revisions`: earlier_id/later_id foreign keys, receipt ID at which the explicit correction relationship was identified, and required evidence text. No observation is updated or deleted. Links require the same source/ticker and an earlier observation ID; no cycles are allowed. The first evidence for a given pair is retained.

This stores decoded yfinance messages, not original protobuf/network bytes. Missing decoded fields stay missing; unknown future fields are retained. Database writes are transactional (`BEGIN IMMEDIATE`, foreign keys enabled, commit before the receiver emits success). A failed record rolls back all its rows. Concurrent writer order is lock/commit order, not guaranteed network arrival order across multiple processes; the current receiver is single-process/single-callback.

## Exact-repeat and conflict rules

An exact repeat means the same source namespace and identical canonical decoded JSON: sorted object keys, compact spacing, original value types preserved. Key ordering/whitespace do not create new observations; number 100 and 100.0, string numbers and numeric numbers remain distinct representations. Full JSON equality avoids hash-collision assumptions. Arrival time is not part of identity. Without provider event IDs, two genuinely different events with identical decoded contents are indistinguishable; their separate deliveries are nevertheless preserved.

Yahoo's observed `id` is a ticker, not an event ID. Neither same ticker nor same timestamp proves a correction. Any payload change (including price or volume) creates a distinct observation even at the same source time. The receiver does not infer revision links. The recorder accepts an explicit revision_of plus evidence only when an upstream source/caller can establish a correction; tests label their fabricated correction marker. No such evidence has been observed from Yahoo so far. Both ambiguous observations remain available to readers.

## Ordering and readers

For delivery replay, order by receipt_id, preserving UTC receipt_time as well. Source ordering uses source_time_ms then observation_id as a deterministic tie-breaker; absent/unparseable times remain null and should be handled explicitly. Receipt IDs are durable recorder sequence numbers, not Yahoo sequence numbers. Late source times do not change prior rows.

For unique-message analysis, query `observations` once per observation_id. Do not join deliveries and count each matching row as a separate market observation. To replay distinct observations known by receipt N:

```sql
SELECT o.*, MIN(d.receipt_id) AS first_receipt_id
FROM observations o JOIN deliveries d USING(observation_id)
WHERE d.receipt_id <= :receipt_cutoff
GROUP BY o.observation_id
ORDER BY first_receipt_id;
```

Apply only revision links whose identified_at_receipt_id is within that cutoff if constructing a corrected view. Raw history remains unchanged. Two same-time changed messages cannot automatically be collapsed into a latest-price or revised-candle rule; aggregation policy is outside this recorder task.

Deduplicating messages does not turn `day_volume` into event volume. Never sum cumulative volume values across observations or deliveries. The constructed test uses day_volume="1200" to prove field retention, not to verify Yahoo volume semantics. Actual live volume remains as documented in feed-investigation.md.

Derived one-minute rules now exist in [candle-aggregation.md](candle-aggregation.md). Aggregation reads this append-only schema and honors revision identification receipt cutoffs; it does not persist or overwrite derived candles.

## Chart configuration storage

Named indicators use a separate `chart-settings.sqlite3`, configurable with MARKET_SETTINGS_DB_PATH; they never write into session observations/deliveries/revisions. `indicator_instances` stores ID, symbol, source, timeframe, name, type and validated settings JSON, with a unique chart/name constraint. See the complete [schema and initialization rules](indicators.md). The first valid API save initializes the table; invalid input does not alter saved instances.

## Paper account tables

The explicitly requested simulated account adds `paper_accounts`, `paper_positions`, `paper_orders`, `paper_fills` and `paper_requests` to the existing MARKET_DB_PATH file. It does not rewrite observation/delivery/revision records. Stable request IDs and unique fill/order relationships enforce retry safety. `BEGIN IMMEDIATE` covers cash/shares/fill/order/cursor mutations together; money is integer cents. Replay accounts retain their own cursor and selection. See [schema responsibilities and execution rules](paper-account.md) and the canonical DDL in backend/paper.py.

## Paper P&L history

`paper_pnl` adds immutable event snapshots linked to account/symbol/fill/observation and receipt knowledge. Unique `(account_id,symbol,event_key)` prevents repeated fills or candle close events from duplicating rows. Exact rational cents preserve fractional weighted-average cost; dollar projections simplify inspection. Initialization reconstructs existing fills but does not invent prior candle marks. See [full fields and identity rules](pnl.md) and canonical DDL in backend/pnl.py.

## Decision evidence

`decision_snapshots(id,created_at,digest,snapshot_json)` freezes chart, source/receipt/revision evidence, SMA values and historical simulated balances. Update/delete triggers preserve snapshot immutability. `decisions(id,snapshot_id,created_at,completed_at,provider,model,status,result_json)` links each attempt and saved proposal/validation/explanation to that evidence. A pending insert commits before network I/O, then the terminal status commits. Canonical DDL is backend/decisions.py; [detailed contract](decisions.md). These routes never initialize or advance paper accounts. New replay-account spec_json also records initial_step for causal account-existence checks; older replay accounts without it cannot yield eligible decision snapshots.

## Chart capture evidence

`decision_images(decision_id PRIMARY KEY REFERENCES decisions(id), snapshot_id REFERENCES decision_snapshots(id), png BLOB, sha256, width, height, questions_json)` retains validated chart-only PNG bytes. Result JSON retains named answers, expected Python crossover, comparison, eligibility, question text and retrieval URL. Saved snapshot JSON now includes capture_range and range-filtered chart/SMA/named-indicator values computed using preceding history. No observation or paper ledger rows are changed. [Validation and limits](chart-analysis.md).

## Reviewed decisions

No new table is required. Existing decisions.result_json now holds roles.analyst, roles.reviewer and final_check; the single snapshot_id and decision ID remain unchanged. Each role records model/provider, visible categorical outputs, questions, timestamps, call count, snapshot digest and optional identical image hash. Analyst evidence commits before review; review_pending has null completed_at and false eligibility. The final update records reviewer verdict and Python account/strategy/evidence enforcement. Legacy records remain unchanged. [Details](decision-review.md).

## Paper automation extension

`automation_controls` stores account, strategy (including SMA windows), symbol, interval, enabled flag, generation and Start baseline. Its scope tuple is unique. `automation_jobs` stores that scope plus candle, snapshot/decision IDs, state/reason, order/fill IDs, creation/expiry times and execution result JSON. `(account_id,strategy,symbol,interval,candle)` is unique and decision_id is unique. UTC candle keys are canonicalized before reservation.

Nullable `decision_id` columns link `paper_orders`, `paper_fills` and `paper_pnl` to the saved review. Orders/fills each have a unique partial index on non-null decision IDs. Manual rows remain null. Schema initialization is idempotent and automatic at startup. The simulator fill transaction includes all these links and the automation job result, so failure rolls back balances, shares, fill and P&L together. Stop/restart cancels pending jobs/orders but preserves decision evidence, completed fills and durable claims. See [policy](paper-automation.md).


## Deterministic SMA strategy extension

[Strategy schema and transaction rules](sma-strategy.md) add `sma_runs` and `sma_events` on first strategy API use. `sma_runs.account_id` uniquely references an isolated `paper_accounts` row with mode `strategy`; `sma_events` uniquely identifies run/candle, references the known delivery and optional shared paper order, and freezes decision/account-before facts. Existing fills/P&L retain execution and result history. The strategy cursor, events, orders and shared fills/P&L commit atomically under `paper.process_live`. Stop disables the run and rejects pending orders in a serialized write transaction. No observation table or historical fill is rewritten.


## Historical backtest storage

Each ignored `backend/data/backtests/<run-id>.sqlite3` contains its own source snapshot and shared paper ledger, plus `backtest_run(id, metadata, frozen_input, status, result, error)`. Metadata records immutable selection/cutoff/hash, policy/configuration, execution assumptions and code/dependency identifiers. Results retain decision/order/fill/valuation trace and performance. Recorded source SQLite is read-only; no production-account row is used for execution. Historical-bar adapter receipts are labeled as derived availability events, not live Yahoo receipts. [Full semantics/API](backtesting.md).

### Backtest presentation extension (Prompt6)

The existing per-run `backtest_run.result` JSON now includes `chart`: frozen final-known candles/status, Python SMA values/signals and a history-versus-decision label. No shared live-ledger migration. `metadata.run_id` makes exported JSON traceable. Dataset catalog/list/read endpoints are read-only; completed-result GET never advances paper execution. Empty API evaluation persists status `failed` with an explanatory error, without fabricated results. Saved selection in browser localStorage is only an ID; SQLite remains authoritative across restarts. Older results missing `chart` derive it from `frozen_input` on read without writes.

Submission reproducibility: `python3 -m backend.recorder init` creates the observation/delivery/revision schema on a fresh configured database; paper/settings tables initialize when their corresponding services are used. Backtest databases initialize per run under MARKET_BACKTEST_DIR and persist frozen input/metadata/results. The submission checker uses temporary paths and confirms returned results equal stored JSON. Runtime/evidence-copy databases stay ignored; exported JSON/screenshots/video are curated separately. A source export with reused dependencies is not a verified checkout of the final submitted commit.
