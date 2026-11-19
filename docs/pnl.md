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


## Part 4.2 accounting reconciliation — November 17, 2026

Reused prompt09d and the existing weighted-average implementation; no accounting algorithm was replaced. Independent expectations are in [accounting_reference.py](../backend/accounting_reference.py). The fixtures exercise the real execution/valuation path; expected values are hand-derived constants, not outputs from the production ledger function.

```sh
python3 -m unittest backend.test_pnl backend.test_paper -q
python3 docs/accounting_check.py
```

The second command creates three disposable databases, uses the installed Chromium, and compares direct SQL rows with API responses and every displayed P&L amount. For each case it stops the backend and starts a fresh process against the same database, repeats the browser checks, and verifies all rows and source-record hashes remain unchanged. The account named `live` exists only in each temporary fixture database; the user's market database is never used. Yahoo is disabled and the model key removed. Owned processes/browser are stopped. Logs and full transient artifacts are under ignored `test-results/accounting/`.

### Five-event reference

All amounts below are dollars; expected and observed agree at each row.

| Event | Cash | Shares | Realized | Unrealized | Total P&L | Equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Buy4 at100 | 600 | 4 | 0 | 0 | 0 | 1000 |
| Completed mark110 | 600 | 4 | 0 | 40 | 40 | 1040 |
| Sell1 at110 | 710 | 3 | 10 | 30 | 40 | 1040 |
| Completed mark95 | 710 | 3 | 10 | -15 | -5 | 995 |
| Close3 at105 | 1025 | 0 | 25 | 0 | 25 | 1025 |

### Independent multiple-buy and rounding example

Observed raw quotes100.005,101.014 and102.005 fill at100.01,101.01 and102.01 respectively. This checks decimal ROUND_HALF_UP at the fill boundary. Buy2, buy1, then sell1. Total acquisition cost is301.03, so average cost is301.03/3 =100.343333… per share. It remains unchanged after the partial sale; display rounding to100.34 never feeds back into accounting.

| Event | Cash | Shares | Exact average cost | Realized | Unrealized | Total P&L | Equity |
| --- | ---: | ---: | --- | --- | --- | ---: | ---: |
| Buy2 at100.01 | 799.98 | 2 | 100.01 | 0 | 0 | 0 | 1000 |
| Buy1 at101.01 | 698.97 | 3 | 301.03/3 | 0 | 2 | 2 | 1002 |
| Sell1 at102.01 | 800.98 | 2 | 301.03/3 | 5/3 | 10/3 | 5 | 1005 |
| Completed mark103.125 | 800.98 | 2 | 301.03/3 | 5/3 | 1669/300 | 7.23 | 1007.23 |

At the last row, equity =800.98 +2×103.125 =1007.23. Realized5/3 plus unrealized1669/300 equals7.23. Vue shows1.67 realized,5.56 unrealized and7.23 total. The valuation retains103.125 internally and displays103.13; unlike executable fills, completed-candle marks are not rounded to cents before calculating P&L.

### Assumptions, unavailable values and invariants

This remains a zero-fee, zero-slippage/spread, full-fill, long-only observed-price simulation. Orders fill only on later eligible receipts and recheck cash/shares. No claim is made about exchange liquidity or achievable execution; stale newly received quotes may fill. See [execution rules](paper-account.md). Weighted-average basis is exact fractional cents; SQL/JSON dollar projections are floating point and Vue rounds for display. Exact stored fractions and independent expectations are compared with zero tolerance; browser checks compare the expected two-decimal formatting.

For each valid row the checks independently calculate equity = cash + quantity × mark, total P&L = realized + unrealized, and equity − initial1000 = total P&L. These are verification calculations; this step adds no new equity UI or schema. An invalid latest completed close in the third fixture produces unavailable mark/unrealized/total/equity, while preserving realized P&L and earlier history. Vue must display **Unavailable**, not zero. The last valid price does not automatically expire merely because it is old; source/time labels distinguish availability from freshness.

Tests also check exact event/request retries, rejected oversells, nonnegative cash/positions, and rollback after an injected P&L-insert failure: cash, position, fill, order status and receipt cursor remain at their prior state; retry recovers one fill. Hashes cover all fields of observations, deliveries and revisions before/after account reads, retries/rejections and real backend restart. Source records remain unchanged.

One initial expected-value discrepancy was in the new audit fixture, not production accounting: after the second buy, per-share gain is2/3 dollars across3shares, so total unrealized is2 dollars. The first expected constant mistakenly used2/3 as the total; correcting that independent reference resolved the failure. No production accounting change was needed. A small CSS change keeps currency amounts and Unavailable labels from wrapping mid-value in the P&L table.


Final evidence: [summary with exact expected/observed rows](evidence/accounting-part42/result.json); [standard before SQL](evidence/accounting-part42/standard-before-sqlite.json), [after SQL](evidence/accounting-part42/standard-after-sqlite.json), [before API/browser](evidence/accounting-part42/standard-before.json), [after API/browser](evidence/accounting-part42/standard-after.json); [multiple-buy before](evidence/accounting-part42/multiple-before.json), [after](evidence/accounting-part42/multiple-after.json); [unavailable before](evidence/accounting-part42/unavailable-before.json), [after](evidence/accounting-part42/unavailable-after.json). Screenshots: [five-event result](evidence/accounting-part42/standard-after.png), [multiple buys](evidence/accounting-part42/multiple-after.png), [unavailable](evidence/accounting-part42/unavailable-after.png). All three cases passed all before/after comparisons; owned processes stopped.
