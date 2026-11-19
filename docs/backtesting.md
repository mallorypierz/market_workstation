# Part 4.2 historical backtesting

Published implementation/evidence [8565d23](https://github.com/mallorypierz/market_workstation/commit/8565d239f94a356f91cbd47054e416e8bc465345); [remote CI](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) **success**; [59-second video](https://raw.githubusercontent.com/mallorypierz/market_workstation/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part-4.2-demo.webm) verified by unauthenticated full download and matching SHA256. The exact committed checkout passed tests/build/browser checks with reused local dependencies. Student review and Canvas upload remain the student’s actions.

Implemented November17,2026, reusing the verified SMA crossover policy and weighted-average paper accounting. Backtesting evaluates decisions, pending/rejected orders, fills, valuations and account performance; chart replay alone does not do this. This step provides Python/CLI and FastAPI results. The dedicated Vue backtest screen is implemented and verified, as described below.

## Run and retrieve

Existing dependencies only; no model/provider key, real broker or installation is needed. Normal localhost startup is unchanged. Runtime files are isolated under ignored `backend/data/backtests/`, configurable with `MARKET_BACKTEST_DIR`. Input SQLite is opened read-only. Each backtest has its own SQLite database and `backtest` account; the production account is never passed to execution.

Recorded Yahoo example (use a new stable ID for a new run):

```sh
python3 -m backend.backtest my-recorded-run --warmup-start 2026-11-12T14:22:00Z --start 2026-11-12T14:30:00Z --end 2026-11-17T00:00:00Z
```

Real historical daily-bar example:

```sh
python3 -m backend.backtest my-daily-run --bars docs/evidence/aapl-2025-daily.json --warmup-start 2025-01-06T00:00:00Z --start 2025-01-13T00:00:00Z --end 2025-03-01T00:00:00Z --timeframe 1d
```

Optional CLI `--source` selects a recorded SQLite file and `--output` exports results JSON. `--short`/`--long` default2/3. Library `backtest.run` also accepts positive `initial_cash_cents` (default100000, max1e12) and optional recorded `snapshot_cutoff`; sizing is fixed to one share. Invalid identity, dates, windows, source type or split-containing bar data is rejected.

- POST `/api/backtests`: JSON `run_id`, `start`, `end`, optional `warmup_start`, `short`, `long`, `timeframe`, `initial_cash_cents`, `snapshot_cutoff`, `dataset`. Dataset is `recorded` (configured source database) or `aapl-2025-daily` (the retained historical artifact); arbitrary filesystem paths are not accepted over HTTP.
- GET `/api/backtests/{run_id}` returns frozen metadata, status, error and completed result without rerunning it.
- Repeating an ID with the same request returns its saved result even if new source receipts arrive. Changed parameters/data identity require a new ID. Running/failed records are not silently re-executed. If execution is interrupted, a record may remain `running`; inspect it and use a new ID rather than assume completion. Concurrent requests for an ID still initializing may return storage-unavailable; retry after initialization.

## Frozen inputs and persistence

[backtest.py](../backend/backtest.py) normalizes UTC selection and reads a consistent SQLite snapshot. Recorded selection includes AAPL Yahoo deliveries in `[warmup_start,end)` by original receipt time, at/below the frozen receipt ceiling. Selected observations and their applicable explicit revision links are copied into the run database with original identities. Source tables are not updated. The stored `frozen_input` JSON preserves the full chosen input, independent of later source edits/deletion.

`backtest_run` stores one row: immutable metadata/configuration/provenance/input, status (`running`, `completed`, `failed`), results JSON and error. The same file also stores the actual isolated `paper_accounts`, positions, orders, fills, request receipts and P&L tables. The library's unused default account is local to this run database; all backtest actions use mode `backtest`, excluded from ordinary live advancement and manual-order mutation.

Metadata includes run ID (file/API identity), instrument/timeframe, warm-up/evaluation dates, dataset SHA256 and receipt cutoff where applicable, source/retrieval information, SMA windows, initial cash, one-share sizing, policy version, execution/valuation assumptions, Git HEAD, implementation-file hashes and Python/SQLite/package versions. File hashes distinguish uncommitted implementation from the recorded Git commit. Runtime databases stay ignored; curated source/result evidence is retained separately under docs/evidence.

## Warm-up, causality and policy

Warm-up begins at `warmup_start`; evaluation begins at `start` and ends exclusively at `end`. Initial equity is recorded at evaluation start before any trade. A candle whose start precedes evaluation is warm-up only, even if learned later. Such candles can establish averages/last crossover side but never create performance-period trades. Inadequate warm-up produces explicit `SMA warm-up` no-action decisions; the first comparable side establishes state without trading. Missing candles are never zero-filled.

The common `strategy.choose_action` is used by both forward strategy and backtest: confirmed up buys one share when flat/affordable; down closes a position; no shorting, borrowing or pyramiding. Pending orders suppress another submission. Every decision freezes candle/SMA values, receipt boundary, time, action/reason and account-before facts, then links to the saved order/fill. All math remains in Python. Existing AI-reviewed automation is unchanged.

### Recorded observations

Process selected deliveries in receipt-ID order. The logical clock never decreases when receipt timestamps regress. For each revealed receipt: fill older pending orders, advance account cursor, reconstruct candles with the current receipt cutoff, compute SMA, evaluate newly completed candles, and append completed-close valuation. Future observations and future correction links cannot enter this view. Source-time sorting is used only within the known candle view, not to reorder decisions.

Orders have a receipt boundary equal to the decision receipt and can fill only on a strictly later eligible receipt. Shared simulator rules exclude exact repeated deliveries and explicitly identified corrections from executable prices. Changed quotes and newly received stale source quotes may fill, and there is no exchange-session filter for fills. Signals use regular-session completed candles. Fees/spread/slippage are zero, fills are whole/full, prices round HALF_UP to cents and cash/shares are rechecked at fill. This is an idealized observed-price simulation, not achievable execution evidence.

Already evaluated candles are not traded again after late correction. Future signals can use corrected knowledge; prior decisions/fills remain frozen. A repaired older gap behind the processed-candle watermark does not create a retroactive order. No final wall-clock advance invents completion after the last selected receipt.

### Historical daily bars

The retained daily input is distinct from recorded streaming observations. Each supplied session has an exchange-calendar UTC open and close. The open becomes available at open; its high/low/close become available only at close. Pending orders fill at the next **supplied** session open, never the signal close or the same bar's earlier open. Missing sessions are not synthesized. Only completed-prefix OHLC enters SMA.

The adapter stores explicitly labeled `historical-yahoo-bars` open/close events (or `synthetic-daily-bars` for tests) to use shared execution. These are simulated availability events, not original Yahoo receipt timestamps or reconstructed tick history. No original revision history exists for this dataset; historical values reflect the download snapshot. It cannot prove real-time point-in-time data quality. High/low are not used for execution or an intraday path.

Raw downloaded OHLC was requested with auto_adjust=False, back_adjust=False, repair=False and actions=True, as supported by [yfinance's history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html). This is a **price-return** study: cash dividends are not credited or reinvested; split-containing selections are rejected rather than silently applying incorrect share accounting. Yahoo historical prices can reflect vendor corrections/adjustments; no as-traded historical revision audit is claimed.

## Valuation and metrics

After each evaluation receipt (recorded mode) or completed daily close (bar mode), value holdings at the last positive, finite, known completed-candle close. At an end boundary after a bar open but before its close, use the preceding completed close. This price can precede a recent fill and be stale: it is disclosed in the curve and P&L source/time. No usable completed close means unavailable equity/unrealized/return, not a fabricated zero. Shared `pnl.append` and `pnl.ledger` compute exact weighted-average realized/unrealized amounts; fill rows retain their original execution-price valuations, followed by the backtest completed-close mark.

Keep open positions and pending orders at end. No forced closing trade or assumed liquidation price is added. Results include account cash/positions, all orders/fills, decision trace, valuation history, current realized/unrealized P&L, pending orders, equity curve and sample sizes.

- Equity = cash + shares × known completed mark; flat-account equity is cash.
- Total return = `(ending equity − initial equity) / initial equity`. This is simulated price-only portfolio return, not dividend-inclusive investment return.
- Maximum drawdown = maximum `(running peak equity − equity) / running peak equity` over sampled curve points, including initial cash. It is not intrabar drawdown. If any sampled equity is unavailable, full-curve maximum drawdown is unavailable.
- Exact rational metric forms are persisted alongside JSON numbers. No annualization, parameter optimization, benchmark or profitability requirement is introduced. Identical frozen inputs/configuration give identical decisions, fills, valuations and metrics; processing/creation timestamps and metadata identifiers can differ across new runs.

## Verification and actual evaluation

```sh
python3 -m unittest backend.test_backtest -v
python3 docs/backtest_check.py
```

Synthetic tests cover hand-known $1000 → buy1@$100 → close1@$110 = $1010,1% return;9.9% sampled drawdown under the specified completed-close marks. Tests also cover no trades, inadequate warm-up, warm-up exclusion, pending/no-next-price in both modes, end valuation of open shares, duplicates, late corrections/clock regression, repeatability and source/account isolation. Future-observation/correction changes leave earlier frozen decisions/fills unchanged; changing a future bar's close cannot change its already executed open fill or prior curve. Real HTTP checks compare API and actual persisted SQLite results across backend restart and verify422 validation.

The saved Yahoo capture contains223 deliveries but only **two regular-session one-minute candles**. Its [recorded evaluation](evidence/backtest-recorded-yahoo.json) produces0fills and$1000 ending equity; this establishes insufficient warm-up, not an effective strategy test. Source observations remain read-only.

Separately downloaded [AAPL daily dataset](evidence/aapl-2025-daily.json): January6–February28,2025,37supplied bars; retrieval timestamp and exact request are retained. Four bars precede the January13 evaluation start;33are evaluated through February28. Period/windows were chosen before results and were not tuned for a positive return. The [real historical evaluation](evidence/backtest-yahoo-daily.json) uses2/3 windows, $1000 and one share. It produces10fills, no final holdings/pending orders, **$999.64 equity, −$0.36 realized P&L, −0.036% return and approximately1.2997% sampled maximum drawdown**. It includes a0.25-per-share February10 dividend that is explicitly not credited; the result is price-only, not total investment return.

The sample is short, one currently surviving stock and one chosen period. It does not address survivorship bias or establish out-of-sample performance. Missing trades/quotes, vendor revisions, simplified liquidity/costs, stale recorded marks and sampling frequency limit interpretation. Parameter tuning on this same sample would risk overfitting. Neither a positive nor negative result establishes future performance. No live-stream availability or real fills are claimed by these backtests.


Retained integration evidence: [HTTP/restart/SQLite summary](evidence/backtest-http-result.json), [hand-verifiable API result and full trace](evidence/backtest-http-response.json). The latter has$1010 ending equity,1%return and9.9%completed-close sampled drawdown. It is explicitly synthetic, separate from the real historical evaluation.

## Vue controls and saved results (Prompt 6)

Start the existing backend (`python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`) and frontend (`cd frontend && npm run dev`), then open http://127.0.0.1:5173 and scroll to **Historical backtest**. No model credentials or installation is required. SQLite initializes on first run in `backend/data/backtests`; `MARKET_BACKTEST_DIR` overrides that directory. Keep it across restarts to retain results. The live ledger is separate.

Choose an available dataset, AAPL, a supported timeframe, UTC warm-up/start/end (end exclusive), short/long positive integer windows and positive starting dollars (at most two decimals). Historical daily bars require 1d. Available bounds/counts are shown; they are capture bounds, not a promise of a completed candle in every interval. Empty evaluation selections return a useful error. There is no synthetic fallback. Warm-up contributes indicators but no pre-period trades.

`GET /api/backtest-datasets` returns provenance/bounds/options. `GET /api/backtests` lists saved identities/status. `POST /api/backtests` validates a strict request model (including integer cents/windows, symbol/timeframe/dataset and unknown fields); Python checks ordered windows, timezone and range/data semantics. `GET /api/backtests/{id}` loads a saved result without evaluating or filling orders. An empty POST returns422 and retains a failed run for inspection. Storage failures return503. Requests are synchronous; browser status shows running while pending. A disconnected request may still finish: refresh/load the saved ID before creating a new run. Interrupted running records are inspectable, not automatically resumed.

Vue shows completed/failed status, immutable configuration/provenance/hash/assumptions, two Python SMA series, crossing arrows, equity, return/drawdown, account values and every decision (including skips), linked order status and fill IDs/prices/boundaries. Expand rows for detail. No valuation is displayed as zero when unavailable. Final-known chart history can differ from decisions frozen before a revision; it is explicitly labeled. JSON contains the full equity trace; same-second plotted samples use the last value. Loading older results may derive their missing presentation chart from frozen input, without changing any ledger or rerunning strategy decisions.

Run `python3 docs/backtest_ui_check.py` for real Chromium interactions, invalid windows, fractional API windows, empty data, pending/no-next-fill, full real historical evaluation, refresh, actual backend outage/restart and direct SQLite reconciliation. It creates disposable databases, needs localhost permission in sandboxed environments, installs nothing and stops owned processes. Evidence: [result](evidence/backtest-ui/result.json), [saved JSON](evidence/backtest-ui/response.json), [chart and decisions](evidence/backtest-ui/before.png), [pending order](evidence/backtest-ui/pending.png), [empty range](evidence/backtest-ui/empty.png), [backend outage](evidence/backtest-ui/failure.png), [after restart](evidence/backtest-ui/after.png).

Current limitations: AAPL only; synchronous local execution; no automatic interrupted-run recovery or pagination for very large histories; daily data lacks original receipt/revision history and excludes dividend income. The real historical browser verification remains a separate focused command. Push CI now includes a constructed Part4.2 strategy/backtest scenario in both offline smoke runs, plus Python correctness tests and the Vue build. Final Part4.2 report/commit/video remains separate work.
