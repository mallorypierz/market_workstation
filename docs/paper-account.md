# Local long-only paper account

This explicitly authorized extension is a simulation, not broker integration. It uses the existing MARKET_DB_PATH SQLite file, alongside observations/deliveries/revisions. The first paper API call initializes tables idempotently and creates account `live` with $1,000. Restarting never resets an existing balance. The historical account/recorded session is not deleted. No new package is required.

## Execution and simulated fill rule

`backend.paper.execute(db, request_id=..., action=..., symbol='AAPL', quantity=..., account_id='live')` is the single submission function used by FastAPI and available to a later decision caller. Initialize/open the database with `paper.open_account_db()` first and close it afterward. No decision agent is implemented here.

- Buy/sell quantities must be positive whole integers (booleans/fractions/strings are rejected; supported integer range1–2147483647). Sales above current holdings are rejected immediately and recorded as rejected orders.
- Close accepts no quantity. It queues a sell of the whole holding and resolves the full quantity again at fill, so earlier pending orders cannot leave an unintended residual position. Closing an empty position is rejected.
- Hold retains an existing holding; wait requires cash-only state. Neither creates an order or fill. Inapplicable hold/wait returns a rejected no-order response. Request receipts are retained for idempotency.
- A valid order is **pending**, not filled at the last stored/chart price. Its boundary is the maximum durable receipt ID at submission (or the current replay receipt). It waits for a later eligible observed price for its symbol. There is no timeout/cancellation feature in this first version.
- Eligible means the first delivery of a positive finite decoded Yahoo-shaped AAPL price after the order's receipt boundary. Exact repeats and explicitly identified corrections are skipped. Other changed messages are retained as distinct quotes, matching recorder identity rules. Numeric quotes must round to positive cents and be within the supported storage bound (at most1e12 cents). Missing/invalid prices leave the order pending for the next eligible arrival.
- Arrival order, not retrospective source-time sorting, controls execution. A newly received late source message may be eligible; source age is not a freshness gate in this simple simulator. The source timestamp/raw payload remain traceable through the linked observation. Historical corrections never retroactively change a recorded fill.
- Pending orders are processed in order-ID order at each arrival, all at that observation's price. Full fills only, zero fees, no bid/ask spread, slippage, depth/liquidity model or exchange-session filter. This is intentionally a simplified observed-price simulation, not a claim about achievable market execution. It operates independently from the regular-session candle filter.
- Cash and shares are rechecked at fill. Unaffordable buys or now-oversized sells become rejected with a reason; they do not overdraft or short. Funds/shares are not reserved at submission, so conflicting pending orders can be accepted initially and rejected later.
- Money is integer USD cents. The observed price is rounded to cents with decimal ROUND_HALF_UP before multiplication; original precision remains in the observation payload. Cash is never computed with binary floating-point arithmetic. Account overflow is rejected. Fees are stored explicitly as zero.

The feed callback persists the observation first, then calls `process_live`. Paper account reads/submissions also catch up any unprocessed receipts, allowing a restart after observation persistence but before execution. A cursor advances atomically with processing. Reading an account may therefore complete pending orders against already-arrived post-submission prices; it never fabricates a new market observation.

Each matching batch uses `BEGIN IMMEDIATE`. Fill insert, cash update, position update, order status and processed cursor commit together; any failure rolls everything back. Orders have unique stable request IDs; fills have unique order IDs. Duplicate retries return the original order's current status. Reusing an ID with changed account/action/symbol/quantity is rejected. Vue generates a UUID once per new action, stores the last request locally before sending, and **Retry last request** resends exactly that payload. Repeatedly pressing Buy is a new intended action, not a retry.

## Replay

The original chart replay GET still reads recorded observations without editing them. Selecting Replay exposes **Start new replay paper account**. This creates a separate $1,000 simulation account in the same database, bound to the symbol, UTC receipt range, fixed snapshot cutoff and current step. It never resets or uses the live account.

Only subsequent selected receipts revealed by replay advance can fill its orders. Already-revealed observations cannot fill newly submitted orders. The UI serializes replay advancement and submission and synchronizes to the displayed step before submitting. Fast-forward processes intervening receipts individually in arrival order; it cannot fill all orders at the final candle. Advancing the same step again is idempotent. Backward advancement is rejected; start a new paper replay account to rewind. Changing the selected range detaches the prior account in the UI; its records remain stored. A new replay account started midway begins with cash and sees only later arrivals.

Replay execution time is the original receipt timestamp; processing time separately records current wall time. Submission time is the current replay receipt time (range start at step0). Equal clock timestamps do not obscure causality because receipt boundaries enforce strictly later arrival IDs. The account ID and selection persist in SQLite; browser refresh returns to the live account by default. Existing replay accounts can be inspected through the account API by ID; automatic UI session restoration is not implemented.

## Tables and API

`paper_accounts`: ID, mode, cash_cents, starting_cash_cents, created_at, cursor, replay_step, selection JSON. `paper_positions`: account/symbol primary key and nonnegative quantity. `paper_orders`: ID, account, unique request ID, symbol, action/side, quantity, original requested-quantity JSON, submission time, receipt boundary, status and rejection reason. `paper_fills`: ID, unique order FK, observation/receipt FKs, price_cents, quantity, fee_cents, execution time and processing time. `paper_requests`: unique request ID, canonical request payload, optional order FK and no-order response.

All table definitions are in `paper.initialize`. `paper_orders.quantity` records submitted quantity for buy/sell; close resolves the final whole-position quantity at fill, while action/original request JSON preserve its intent. Monetary/position CHECK constraints and FK relationships supplement transactional validation. Recorded observations, deliveries and revisions are not modified by paper operations.

- GET `/api/paper/account?account_id=live`: consistent snapshot, balances, orders and fill trace; catches up live arrivals.
- POST `/api/paper/actions`: request_id, action, symbol, quantity, account_id. Business rejection is a recorded order/no-order result with `status=rejected`; malformed/unsupported/idempotency-conflict requests return422 without an order.
- POST `/api/paper/replay`: account_id beginning `replay-`, symbol, start, end, snapshot_cutoff, step. Same ID/selection is idempotent. Yahoo must be disconnected.
- POST `/api/paper/replay/advance`: account_id and nondecreasing step. Yahoo must be disconnected.

Localhost and one application worker remain the supported deployment model. No login, real orders, deposits, borrowing or short positions are provided. The original Part4.1 exclusions remain for unrequested trading/AI/audio features.

## Repeatable verification and disposable fixture

```sh
python3 -m unittest backend.test_paper -v
python3 -m backend.paper_fixture init
```

The second command prints a new absolute path in a `paper-fixture-*` temporary folder, initialized with $1,000 and no observations/orders/fills. Set MARKET_DB_PATH to that exact path; use a settings path in the same disposable folder to isolate indicator preferences. Start:

```sh
MARKET_DB_PATH=/printed/paper-fixture-folder/account.sqlite3 MARKET_SETTINGS_DB_PATH=/printed/paper-fixture-folder/settings.sqlite3 MARKET_DATA_LABEL='CONSTRUCTED PAPER ACCOUNT — controlled test prices, not Yahoo data' MARKET_FEED_ENABLED=0 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
npm --prefix frontend run dev
```

In localhost:5173 submit Buy4 and verify pending before supplying price100. Then Sell1 before price110, then Close before price105. Supply each price from another terminal, replacing the path:

```sh
python3 -m backend.paper_fixture price --database /printed/paper-fixture-folder/account.sqlite3 --price 100
# After submitting Sell1 in Vue:
python3 -m backend.paper_fixture price --database /printed/paper-fixture-folder/account.sqlite3 --price 110
# After submitting Close in Vue:
python3 -m backend.paper_fixture price --database /printed/paper-fixture-folder/account.sqlite3 --price 105
python3 -m backend.paper_fixture snapshot --database /printed/paper-fixture-folder/account.sqlite3
```

The helper refuses paths outside an absolute `paper-fixture-*` directory and never defaults to the captured market database. Each message carries a constructed-test label. Yahoo stays disabled. The source uses the same decoder/recorder/execution path; this is not live-source evidence. If run outside the exchange session, the chart can correctly be empty while paper fills still use supplied observations.

Retry an action with the Retry button; attempt a sell when empty. Restart Uvicorn with the same environment/path and refresh the browser. Expected final state: $1,025, zero shares, three fills, four orders including the rejected empty sale. Stop both services with Ctrl+C. Full results and limitations are in [verification](verification.md); [SQLite/API comparison](evidence/paper-check.json) and [browser after restart](evidence/paper-account-restarted.png).
