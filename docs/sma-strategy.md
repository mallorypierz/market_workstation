# Deterministic SMA paper strategy

Part 4.2 extension authorized November17,2026; reuses prompts09c/09d and Prompt3 in [the sequence](../prompts/19-part-4.2-prompt-sequence.md). This is local simulation, not real brokerage or a historical backtest. The existing AI-reviewed automation remains a separate workflow with its original checks.

## Start, inspect and stop

Use the normal README localhost startup commands. In **SMA strategy · simulated only · no AI**, choose short/long positive integer windows with short < long and an existing supported timeframe. Press **Start new SMA run**. Each run creates a distinct `strategy-<run-id>` account with $1,000. Configuration is immutable and shown with the run/account IDs. Existing completed history supplies warm-up only; it does not trade retrospectively at Start.

**Retry SMA start** resends the saved request ID/configuration; it does not create another account or restart a stopped run. Saved runs can be selected after refresh, and the last selection/request persists locally. Changing the chart windows does not change a running strategy's frozen windows. Starting another run creates another independent account; use the saved-run selector to stop any earlier enabled run.

**Stop SMA run** disables that run and rejects pending orders with `Strategy stopped before fill`. It is terminal: use a new run for new simulation. A stopped run's records remain available. Closing the page does not stop a run. Enabled runs persist across backend restart, and the next receipt callback or account/strategy poll resumes unprocessed receipts exactly once. The UI states these behaviors. Replay chart selection does not drive or reset strategy accounts; new strategy starts are disabled in chart Replay mode. Existing runs still follow forward receipts.

## Policy and execution assumptions

- Only completed, coverage-complete candles qualify. Short/long means and crossovers use existing exact Python SMA logic. Initial comparisons/ties follow [SMA rules](sma.md). No provisional trade signals.
- Upward crossover: buy **one** share only if flat and the signal candle's cent-rounded close is affordable. Downward crossover: close the holding. Otherwise record `SMA warm-up`, `No crossover`, `Already holding; no pyramiding`, `Flat; no position to close`, `Insufficient cash at signal`, or another explicit reason. A pending order suppresses another submission.
- AAPL only, no borrowing/shorting, no pyramiding. Full fills, zero fees/spread/slippage, integer-cent fill prices with ROUND_HALF_UP and existing exact weighted-average P&L. The shared simulator rechecks cash/shares at fill; a later unaffordable quote rejects an otherwise accepted buy.
- Receipt-driven processing uses the durable receipt-ID order and a nondecreasing receipt-time clock. No wall-clock tick creates strategy decisions: without a new receipt, an unfinished candle remains unprocessed even if the chart later displays it as ended. This deliberately avoids wall-clock-dependent recovery results. UI exposes processed receipt/last completed candle.
- At each revealed receipt: mark prior known completed candles, fill previously pending orders, mark current known candles, advance the isolated account cursor, derive SMA using only the current receipt cutoff, and decide newly completed candles in time order. An order created here has `after_receipt` equal to this receipt; the current quote cannot fill it. Later backlog receipts are processed individually, not all at the final price.
- Reuse the existing [eligible-price rules](paper-account.md): first delivery of a positive finite Yahoo-shaped quote, excluding exact duplicate deliveries and explicitly identified corrections. Newly received stale source quotes may fill; no exchange-session, liquidity or freshness execution filter is introduced. Signals use regular-session candles; fills may occur outside that session. This is an observed-price simulation, not a claim of achievable market execution.
- Pending orders have no timeout and remain pending if no later eligible price exists, until Stop. P&L uses existing completed one-minute marks, independent of strategy timeframe; source/valuation times remain visible. No forced liquidation or backtest return/drawdown report is added.

## Causality, revisions and transactions

Each run stores a receipt cursor, monotonic clock and last processed completed-candle timestamp. A unique `(run_id, candle)` event and stable `sma:<run-id>:<candle>` order request identify the decision. Receipt cursor, events, order submission, fills and P&L update inside the existing `paper.process_live()` `BEGIN IMMEDIATE` transaction. Failed processing rolls everything back, leaving the source receipt available for a retry. The recorder's original observations remain untouched.

The run freezes an event's SMA values, crossover, action/reason, known receipt boundary and account-before facts. Later chart corrections can change historical SMA lines/markers, but never rewrite frozen decisions, order prices or fills. A revised candle already at/before the run watermark is not traded again. Late data can influence future newly completed candles; an older gap repaired behind the watermark does not trigger a retroactive order. If one receipt completes several candles, they share the same knowledge boundary; a pending order prevents multiple queued positions.

Stop and processing serialize through SQLite write transactions: either a decision commits before Stop (its pending order is then rejected), or Stop commits first and processing ignores the disabled run. A fill already committed before Stop remains historical fact. No subsequent receipt/poll/retry/start retry creates an event or fill for the stopped run.

Strategy mode is excluded from normal live/test account advancement. Manual paper POST actions cannot mutate strategy accounts. Existing AI automation accepts only its own supported live/test modes, so it cannot attach to these accounts. Manual replay continues using its existing independent replay accounts. No model client or API key is used by the deterministic strategy.

## Files, API and schema

[backend/strategy.py](../backend/strategy.py) owns orchestration; [paper.py](../backend/paper.py) retains the single shared execution/P&L path. [SmaStrategy.vue](../frontend/src/SmaStrategy.vue) displays controls, frozen decisions, linked order/fill status, current balances and P&L history. HTTP endpoints:

- POST `/api/strategy/start`: `run_id`, `symbol` (AAPL), `timeframe`, `short`, `long`. Same ID/config returns the existing run; conflicting configuration returns422.
- GET `/api/strategy`: list saved runs/configurations.
- GET `/api/strategy/{id}`: catch up receipts and return run, events and account snapshot. Thus this read may advance enabled simulations, like existing paper account polling.
- POST `/api/strategy/{id}/stop`: disable and cancel pending orders; repeatable.

Initialization creates two additive SQLite tables in existing `MARKET_DB_PATH` on first strategy API use, with no destructive migration or new dependency:

| Table | Stored information / constraints |
| --- | --- |
| `sma_runs` | run ID primary key; unique account foreign key; AAPL/timeframe/short/long; enabled; receipt cursor, clock, last completed candle and creation time |
| `sma_events` | event ID; run foreign key; unique run/candle; knowledge receipt foreign key; decision time; frozen SMA values/signal/action/reason; cash/shares before; optional paper order foreign key |

Existing orders link to fills, observation/receipt identity and P&L rows. Event API joins order status/rejection and fill ID/price/time/receipt. Current account plus P&L rows provides the resulting balance trace. No model decision ID is fabricated.

## Repeatable verification

```sh
python3 -m unittest backend.test_strategy -v
python3 docs/strategy_check.py
```

The browser check creates temporary `strategy-browser-*` market/settings databases, disables Yahoo, removes the model key, and uses installed Chromium. Its guarded `backend.strategy_fixture` CLI appends constructed quotes only to those disposable paths; there are no fixture mutation routes on the production API. Artifacts are retained under ignored `test-results/strategy/`. It stops owned browser/services. It never installs software or operates a real account.

Unit checks cover warm-up, no crossover, up/down decisions, strictly later fills, unfinished candles, duplicate/corrected receipts, start retry/conflict, process restart, insufficient signal cash, fill rejection, Stop cancellation, isolated accounts, sequential versus backlog equivalence and transactional rollback. Browser checks exercise pending buy, buy1@$100 ($900/1), close1@$110 ($1,010/0, realized$10), page reload, independent-run rejected fill, Stop of a pending order and retry after Stop. Direct SQLite checks reconcile fills and untouched live-account cash. See [verification](verification.md) for observed outcomes and corrections.


Observed browser evidence: [pending order](evidence/strategy-pending.png), [completed trade and linked receipt history](evidence/strategy-filled.png), [rejected fill](evidence/strategy-rejected.png), [stopped run](evidence/strategy-stopped.png), [saved API/browser observations](evidence/strategy-browser.json), [SQLite check and cleanup result](evidence/strategy-result.json). Agent visually inspected the filled/rejected screenshots; values and trace columns are readable. All inputs are explicitly constructed.
