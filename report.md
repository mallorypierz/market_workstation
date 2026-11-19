# Assignment 4, Part 4.2 — Indicators, simulated trading and backtesting

**Implementation, public evidence/video access and remote CI verified.**

- **Repository:** [mallorypierz/market_workstation](https://github.com/mallorypierz/market_workstation).
- **Submitted implementation/evidence commit:** [8565d239f94a356f91cbd47054e416e8bc465345](https://github.com/mallorypierz/market_workstation/commit/8565d239f94a356f91cbd47054e416e8bc465345). This report is finalized in a subsequent documentation-only commit.
- **Video (59.00 seconds):** [Watch or download the Part 4.2 demonstration](https://raw.githubusercontent.com/mallorypierz/market_workstation/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part-4.2-demo.webm). Unauthenticated full download verified; bytes match the locally played and measured recording.
- **Remote CI:** [GitHub Actions run 44444599750 — success](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) for that exact SHA: Python correctness tests, Vue build and two fresh full browser SmokeTest runs passed.

Supporting links below are pinned to the submitted implementation/evidence version, whose earlier preparation notes are historical snapshots. This finalized report supersedes their pending-publication status. The original [Part 4.1 report](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/archive/part-4.1/report.md) and evidence are preserved; its112.08 second video is not used for Part 4.2. Upload **only this report.md** to Canvas after student review. Do not upload source files or ZIPs. Nothing has been submitted to Canvas by the assistant.

## Completed application and design

Python calculates two configurable SMAs, confirmed crossovers, deterministic strategy decisions, simulated execution, weighted-average P&L and historical performance. FastAPI exposes validated requests/results; Vue renders candle/SMA/equity charts, controls and inspectable decisions/orders/fills. SQLite preserves source observations, every receipt, explicit revision links, accounts and isolated saved backtests. The existing AI-reviewed workflow remains separate; the Part 4.2 strategy requires no model API or credentials.

Both windows must be positive integers with short < long. For each symbol/timeframe, an SMA averages the last N **completed** closes, including the displayed candle. Warm-up and unfinished values are unavailable. Exact comparisons precede display rounding. Ties retain the last known side; the first unequal comparable pair establishes a side without a signal. Only a later side change signals.

The strategy buys one share on confirmed up when flat and affordable, closes on down, and records skipped reasons otherwise. No shorting, borrowing or pyramiding. A decision queues an order; only a later eligible observation may fill it. Stable run/request/event identities prevent duplicate execution on retries. Stop fences future submissions and cancels pending orders. Later revisions may change chart history but never rewrite executed fills. Accounts and backtests are separate from live/AI accounts.

[Calculation rules](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/sma.md) · [strategy](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/sma-strategy.md) · [backtesting](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/backtesting.md) · [pipeline](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/design-pipeline.md) · [schema](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/sqlite-schema.md).

## Reference, batch and incremental verification

For closes 13,10,7,13,19,7,1 with windows 2/3, the expected paired values/signals are:

| Candle | Short | Long | Signal |
|---|---:|---:|---|
|1|unavailable|unavailable|none|
|2|11.5|unavailable|none|
|3|8.5|10|none; establish below|
|4|10|10|none; retain below|
|5|16|13|up|
|6|13|13|none; retain above|
|7|4|9|down|

An independent oracle uses bundled SQLite SUM/COUNT window frames and integer cross-products; it imports neither production SMA nor indicator code. A fixed authored30-bar series with windows 3/5 crosses at bars 11 down,16 up,22 down,27 up; bar 30 is16/15.4. All expected outputs, timestamps, gaps and signals match with zero tolerance for these integer fixtures. This is an independent calculation, not third-party certification.

“Incremental” means **recomputing each available receipt prefix**, not a stateful rolling accumulator. All values and signals at every prefix are compared against the reference. Tests cover ties, tiny differences before rounding, duplicates, revisions, late arrivals, missing intervals, incomplete candles and symbol/timeframe isolation. Future corrections are excluded from earlier known-at views. [Reference outputs](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/sma-part42-reference.json) · [oracle](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/backend/sma_reference.py) · [tests](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/backend/test_sma.py).

## Accounting checks

The existing exact weighted-average accounting is retained. In an isolated $1,000 account:

| Event | Cash | Shares | Realized | Unrealized |
|---|---:|---:|---:|---:|
|Buy 4 @ $100|$600|4|$0|$0|
|Mark $110|$600|4|$0|$40|
|Sell 1 @ $110|$710|3|$10|$30|
|Mark $95|$710|3|$10|−$15|
|Close 3 @ $105|$1,025|0|$25|$0|

Independent multiple-buy check: buy 2 @ $100.01, then 1 @ $101.01 gives exact average $301.03/3. Sell 1 @ $102.01: cash $800.98,2 shares, realized $5/3, unrealized $10/3. A completed mark $103.125 gives $1,007.23 equity and $7.23 total P&L. Display rounding never feeds back into cost basis. Executable prices round HALF_UP to cents; marks retain available precision.

At each valid valuation, equity = cash + marked position value, and total P&L = realized + unrealized = equity − starting cash. Missing valuation displays unavailable. Tests check atomic rollback, oversell rejection, nonnegative balances, idempotency, unchanged source records and API/browser/SQLite agreement before/after restart. [Expected/observed accounting evidence](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/accounting-part42/result.json) · [assumptions and examples](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/pnl.md) · [tests](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/backend/test_pnl.py).

## Historical evaluation and causal protections

The recorded Yahoo stream has only2 usable regular-session candles, so its run produces0 trades/$1,000 equity; it is insufficient for meaningful strategy evaluation. A separately identified Yahoo daily dataset contains37 AAPL bars from January6–February28,2025, retrieved November17,2026. The fixed2/3 windows and $1,000 starting cash were selected for explainable verification, not optimized to make a profit. Four bars warm up indicators;33 bars are evaluated from January13. Warm-up trades cannot enter performance.

The historical run has five one-share round trips (10 fills):

| Buy → sell dates (2025) | Buy | Sell | Realized |
|---|---:|---:|---:|
|Jan 16 → Jan 17|$237.35|$232.12|−$5.23|
|Jan 24 → Jan 27|$224.78|$224.02|−$0.76|
|Jan 28 → Feb 3|$230.85|$229.99|−$0.86|
|Feb 6 → Feb 10|$231.29|$229.57|−$1.72|
|Feb 12 → Feb 27|$231.20|$239.41|+$8.21|

Final cash/equity **$999.64**, realized **−$0.36**, unrealized $0, no open positions or pending orders; total return **−0.036%**, sampled maximum drawdown **1.2997%**. Return = (ending equity − initial equity)/initial equity. Drawdown is the largest decline from the running equity peak, including initial cash. [Saved result and trace](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/backtest-yahoo-daily.json) · [source/provenance](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/aapl-2025-daily.json) · [real-history browser/restart result](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/backtest-ui/result.json).

Runs freeze input selection/cutoff and hash, symbol/timeframe/date range, windows, starting cash, policy, assumptions and code/version identity. Receipt runs reveal deliveries/revisions sequentially using known-at filters. They do not precompute decisions from finally revised history. Daily-bar runs lack original receipt/revision history: OHLC becomes available at session close, and orders fill at the next supplied session open. Tests perturb future observations/revisions and verify earlier decisions/fills remain identical. Browser tests rerun a fixed prefix after later receipts exist: earlier decisions/equity stay identical and the pending order cannot acquire a future fill. [Causality tests](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/backend/test_backtest.py) · [SQLite browser checks](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part42-smoke/part42-sqlite.json).

End-of-data orders remain pending; open holdings are marked at the last usable known completed close, without invented liquidation. Prices/candles can be sparse. Receipt execution can accept stale newly received quotes; there is no realistic liquidity model. Assumptions are zero fees/spread/slippage, full fills, regular-session candle formation, no fabricated missing bars, unadjusted daily prices, rejected splits and no dividend income. The dataset includes a $0.25 dividend, so the reported return is price-only.

## Verification, revised approach and limits

Observed local checks:110 Python correctness tests pass, Vue build passes, and two expanded SmokeTest runs pass with fresh databases. Controlled strategy/backtest evidence is distinct from real Yahoo: its constructed $100 buy/$110 sale yields $1,010 equity,1%return and9.9%drawdown. Actual Chromium checks chart values/crossovers, skipped/pending/filled states, invalid/empty parameters, backend outage and saved results after refresh/restart; direct SQLite comparisons confirm no duplicate fills. The workflow runs Python correctness tests and the build before two full browser smoke invocations on push. **The exact submitted SHA passed [remote CI](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750), including both fresh smoke invocations.**

During submission preparation, the resume SmokeTest actually failed: the browser helper read the saved-run selector before its newly created option finished loading. Its subsequent request returned the run list, causing `TypeError: Cannot read properties of undefined (reading 'account')`. Under Prompt19 step8/AGENTS AutoLoop, the test was revised to await the specific POST response and assert the matching selected run ID, rather than reusing a previous “completed” status. No calculation or expected number was changed. [Failure, changed-code explanation and rerun evidence](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/part-4.2-evidence.md).

Startup and source-export verification are documented in the [evidence log](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/part-4.2-evidence.md). A subsequent clean detached checkout of the exact submitted SHA also passed all 110 Python tests, the Vue build and both browser scenarios, and remained clean after removing its temporary dependency symlink. Local checks reused installed Python/Node/Chromium dependencies; remote CI independently installed the declared dependencies in its disposable runner. [README](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/README.md), [agent rules](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/AGENTS.md), [AI-use disclosure](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/AI-USE.md), [current checklist](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/part-4.2-checklist.md) and [detailed verification log](https://github.com/mallorypierz/market_workstation/blob/8565d239f94a356f91cbd47054e416e8bc465345/docs/verification.md) describe reproducibility and outstanding checks.

AAPL is a selected surviving company, not a point-in-time universe including delisted firms: survivorship and selection bias prevent generalizing to the market. One short period, one symbol and five round trips are a small sample with no independent holdout or market-regime validation. Trying many windows/date ranges and reporting the best would overfit; that search was not performed. Costs, gaps, revised historical data and simplified execution can materially change results. Historical profit—even if obtained—would not establish future performance; here the real historical example actually loses $0.36. The synthetic profit proves arithmetic, not an investment edge. This is a local educational simulation, not real brokerage.
