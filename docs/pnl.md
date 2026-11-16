# Paper profit and loss

This explicitly requested extension is a local, AAPL-only, long-only, zero-fee simulation. It is not Part 4.1 live-feed evidence. The existing observation database stays configurable through `MARKET_DB_PATH`; initialization of the paper account also creates `paper_pnl`. No new dependency is needed. Reused prompt: [09d](../prompts/09d-record-profit-and-loss.md).

## Calculation and recording

Python owns every calculation. A buy computes `(old shares × average cost + bought shares × fill price) / new shares`. A sale adds `sold shares × (fill price − average cost)` to cumulative realized P&L. Partial sales retain the average. Unrealized is `open shares × (valuation price − average cost)`; total is realized plus unrealized. Closing sets unrealized to zero and average cost to not applicable. Subsequent buys start a new cost basis while cumulative realized remains.

`backend/pnl.py` reconstructs the ledger in fill order using exact rational cents (Python Fraction); no intermediate average-cost rounding. Existing simulated fills are rounded to integer cents by the execution rule. Candle marks retain their decimal close precision. Exact rational cents are stored as text, dollar projections as SQLite REAL for queries and JSON. Vue formats dollars to two decimals only for display.

Each fill appends a row inside the same transaction as cash, position and order changes. Completed regular-session one-minute closes append valuations for open positions, independent of the chart timeframe. Before processing each receipt, Python completes candles using the preceding knowledge boundary; afterward it considers that receipt and corrections. Live account polling also evaluates interval completion without requiring another quote. No unfinished candle becomes a mark. A candle must end after the latest fill and cannot move the previous valuation's candle-end time backward. A revised close of the latest eligible candle appends a new row; old rows remain unchanged. Older corrections still affect chart calculations but do not retroactively rewrite account history. Changing only high/low without changing the close observation does not create a new price event.

Replay processes only the selected revealed receipt IDs and its monotonic receipt-time clock. Stored future observations and wall-clock time cannot supply replay valuations. Repeating a step or polling a completed candle adds nothing. Replaying trades uses the existing isolated paper replay account; recorded source observations are unchanged.

An invalid/nonpositive/nonfinite price gives an open position `valuation_status=unavailable` with null unrealized and total, never a false zero. Realized remains available. A flat account has zero unrealized. The last available price is not automatically expired: its original timestamp/source remain visible, and availability must not be read as freshness.

## Schema and identity

Canonical DDL: [pnl.py](../backend/pnl.py). `paper_pnl` stores:

- `id`, `account_id`, `symbol`, `event_key`, `event_type`;
- `event_time` (evaluation/execution UTC), `recorded_at` (database recording UTC);
- optional `fill_id`, `observation_id`, `knowledge_receipt`, `candle_timestamp`, `candle_end`;
- `price_time` (source observation UTC), `price_source`, `valuation_status`;
- `cash_cents`, `quantity`, exact rational-cent `price_exact`, `average_cost_exact`, `realized_exact`, `unrealized_exact`, `total_exact`;
- dollar projections `price`, `average_cost`, `realized`, `unrealized`, `total`.

Unique `(account_id, symbol, event_key)` prevents duplicate entries. Fill keys are `fill:<id>`; candle keys are `candle:1m:<start>:close:<observation_id>`. Thus polling/restarting/reprocessing preserves one row per event; a distinct corrected close gets a distinct key. History is returned in insertion order, preserving when information was recorded. `GET /api/paper/account` includes `pnl_history` and `pnl_current`; Vue's expanded P&L table presents these fields without recalculating them.

On upgrade, initialization transactionally reconstructs missing fill rows from persisted fills, with original event/price times and current recording time. It does not fabricate unavailable historical candle valuation rows. Source data and old rows are not overwritten.

## Repeatable fixture check

From the project root:

```sh
python3 -m unittest backend.test_pnl -v
python3 -m backend.pnl_fixture
```

The second command creates a new disposable database and prints its path and five expected rows. It labels the Yahoo-shaped messages as constructed test data and uses deterministic November 9 UTC times. To inspect it in Vue, substitute its printed path and a settings path in the same temporary folder:

```sh
MARKET_DB_PATH=/absolute/fixture/account.sqlite3 MARKET_SETTINGS_DB_PATH=/absolute/fixture/settings.sqlite3 MARKET_FEED_ENABLED=0 MARKET_DATA_LABEL='CONSTRUCTED zero-fee P&L fixture — not live Yahoo data' python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173/ and expand Profit & loss history. Stop/restart only the backend with Ctrl+C and the identical environment, then refresh. Compare with:

```sql
SELECT event_type, cash_cents/100.0 AS cash, quantity AS shares,
       average_cost, price, realized, unrealized, total,
       event_time, price_time, price_source
FROM paper_pnl ORDER BY id;
```

See [observed verification](verification.md) and [before/after query evidence](evidence/pnl-check.json). This workflow requires browser interaction; the structure-only SmokeTest is not a UI pass.
