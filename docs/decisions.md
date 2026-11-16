# Frozen paper-account decisions

This authorized extension proposes an action; it never submits, fills or changes a paper order. The existing execution function is not called by any decision route. Python supplies recorded facts, the provider supplies one choice, and Python validates it. Reused prompt: [10-add-decision-api.md](../prompts/10-add-decision-api.md).

## Separate freeze, inspect and ask operations

1. `POST /api/decision-snapshots` with `{"account_id":"live","symbol":"AAPL","interval":"1m","candle_timestamp":"2026-11-09T14:34:00Z","short":2,"long":3}` freezes a view without a model call.
2. `GET /api/decision-snapshots/{snapshot_id}` returns that immutable view, including its chart candles, completion metadata, SMA series, selected candle/indicators, account, source observations and known revision links. A chart renderer must use this saved `chart` object, not refresh ordinary history. The subsequent [Ask about chart extension](chart-analysis.md) renders these records and provides a frozen PNG analysis panel.
3. `POST /api/decisions` with `{"snapshot_id":"..."}` evaluates the saved view. No client-supplied replacement facts or order quantities are accepted into that snapshot.
4. `GET /api/decisions/{decision_id}` retrieves the persisted result. It references the saved snapshot ID; the SHA-256 digest identifies its exact serialized content.

The snapshot records a separate creation timestamp and decision time. Decision time is exactly the selected candle's exclusive interval end, computed with the existing regular-session exchange calendar and intraday alignment rules. Supported intervals are1m,5m,15m,1h,1d; currently AAPL only. Future, misaligned, missing or incompletely covered candles and SMA warm-up yield an incomplete snapshot, not an executable proposal.

### Knowledge and account boundaries

The freeze runs inside one SQLite read transaction. Delivery ID controls arrival order. Selection stops before the first receipt after candle close, even if a later receipt has a backwards wall-clock timestamp. Exact UTC datetime comparisons preserve microseconds. An optional receipt_cutoff can further restrict known records. Only explicitly linked revisions identified in that visible receipt set apply. Source timestamps assign candles; no next-interval candle enters the saved chart. All prior completed-candle SMA context is retained so tie/crossover behavior matches the existing calculation.

Replay also restricts receipts to the selected range and revealed account step; the replay clock must have reached the requested close. New replay accounts retain `initial_step` in their specification so an account created later in logical replay time cannot be used for an earlier close. Legacy replay accounts without this provenance are incomplete for decisions; create a new replay account. Existing ledger entries remain intact.

Cash and shares are reconstructed from starting cash and eligible persisted fills, not today's balance. Fills require visible receipts and execution at or before close; live fills must also have been processed by then. The live account must already have existed at that close. Replay uses logical receipt/execution time, not physical replay processing time. Pending orders do not reserve funds under the existing simulator; any later execution feature must recheck current balances and pending orders. Creating a decision does not initialize a missing account, process pending orders, or backfill P&L.

Unknown volume remains null and labeled; verified prices and warmed-up SMAs are sufficient for this price/SMA question. Snapshot completeness does not assert a full exchange tick feed or known Yahoo volume. Constructed payloads carrying `test_data`, or an explicit MARKET_DATA_LABEL, force test labeling and order_eligible=false even when all calculation inputs exist. Missing account/indicator/candle inputs also make the snapshot ineligible.

## Provider and validation

The official [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) and [request reference](https://developers.openai.com/api/reference/resources/decisions/methods/create) specify POST https://api.openai.com/v1/decisions, model `gpt-6-luna`, and named choice questions. The backend sends the saved snapshot as JSON text input and one question named `paper_action`, with buy/sell/hold/wait/close choices. It parses the matching named answer and handles refusal separately. Python's urllib, ssl and json provide HTTP/TLS; the already installed certifi bundle supplies trusted roots on this computer. No SDK or new dependency was installed.

`OPENAI_API_KEY` belongs only in the backend process environment. Never put it in Vue, a request body, a prompt file or logs. No dotenv loading is introduced. The provider URL is fixed; no caller-supplied endpoint can receive credentials. HTTP and transport failures store status labels without exception text or response bodies that might echo secrets. The request has a30-second socket timeout and no automatic retry. A timed-out call may have reached the provider; it is never silently resubmitted.

`MARKET_PAPER_ORDER_SIZE` is a positive whole number up to2147483647, default1. This server setting is now exposed by `paper.configured_order_size()` and frozen in each snapshot; it does not change existing manual controls' explicit quantities.

- buy: proposes that size; must fit snapshot cash at the simulator's cent-rounded close price.
- sell: proposes that size; cannot exceed snapshot shares.
- close: proposes the entire snapshot holding; requires an open position.
- hold: valid only with an open position; creates no order.
- wait: valid only while flat; creates no order.

The backend explanation quotes close, SMA values, crossover, cash and shares. It explicitly describes recorded facts rather than inventing a model rationale. `proposal` contains the model's answer. A valid answer is not a recommendation guarantee or an execution instruction. `order_eligible` is only a preliminary snapshot/action gate; all routes leave the ledger untouched, including valid buys/sells/closes.

## Storage and statuses

`decision_snapshots`: immutable UUID, created_at, digest, snapshot_json. Update/delete triggers reject changes. `decisions`: UUID, snapshot_id foreign key, created_at, completed_at, provider, model, status, result_json. Both are in MARKET_DB_PATH, created automatically on first decision API use. Snapshot and decision writes never alter observation or paper tables. The result has snapshot ID, provider/model, separate model_call and market_data labels, proposal, validation, factual explanation and eligibility.

Each POST evaluation has its own decision ID. The initial pending row commits before external I/O; the terminal result commits after. No database lock spans the network call. A crash can leave pending as evidence of an interrupted attempt; there is no automatic retry or order recovery.

| Status | Meaning |
| --- | --- |
| valid | Named allowed action satisfies snapshot account rules, including valid hold/wait |
| invalid_proposal | Allowed action violates cash/position rules |
| missing_input | Snapshot absent or incomplete; provider not called |
| timeout | Provider transport exceeded its socket timeout |
| malformed_answer | Invalid JSON/answer shape, wrong question name, unexpected answer type or choice |
| refused | Provider explicitly refused the named question |
| configuration_error | Backend key not configured; provider not called |
| provider_error | HTTP/TLS/network failure |
| pending | Recorded attempt not yet completed, possibly interrupted |

HTTP200 carries terminal decision statuses with an ID; clients must inspect `status`. Snapshot creation is201, unknown GET IDs404, unavailable SQLite503. A non-object/invalid HTTP JSON body is rejected by FastAPI422 before a decision can be made. Missing fields in an object are persisted as missing-input results.

## Repeatable verification and live check

From the root, using the existing Python environment:

```sh
python3 -m unittest backend.test_decisions -v
python3 -m backend.decision_check
```

The offline check creates a new disposable database, verifies the fixed snapshot and a controlled timeout, compares saved results and proves all six paper tables unchanged. The fixture uses seven synthetic closes13,10,7,13,19,7,1. At14:34 UTC the close is19, SMA2=16, SMA3=13, crossover up, cash1000, shares0. Only the first five receipts belong to that candle-close decision despite later data already being stored. Test data cannot become an eligible paper order.

For one live model call on **test market data**, create a new disposable file:

```sh
python3 -m backend.decision_fixture --database /private/tmp/market-decisions-live-check.sqlite3
```

The command refuses to replace an existing file. In zsh Terminal, configure the key without echoing it or putting the value into command history:

```sh
read -s "OPENAI_API_KEY?Paste your OpenAI API key (hidden): "
export OPENAI_API_KEY
python3 -c 'import os; print("Key configured" if os.getenv("OPENAI_API_KEY") else "Key missing")'
MARKET_FEED_ENABLED=0 MARKET_DB_PATH=/private/tmp/market-decisions-live-check.sqlite3 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --ws websockets-sansio
```

Keep that Terminal open. From a second terminal:

```sh
python3 -m backend.decision_check --live --database /private/tmp/market-decisions-live-check.sqlite3
```

This makes exactly one POST to the decision endpoint, then compares the GET result and direct SQLite record and checks the paper ledger is unchanged. It exits2 if no validly parsed live provider response was obtained. Stop the server with Ctrl+C; `unset OPENAI_API_KEY` removes the key from that Terminal environment. Observed results, rather than instructions alone, are recorded in [verification.md](verification.md).

## Subsequent review extension

The public POST route now wraps this analyst stage with a separate reviewer call and Python final gate. Both use the same snapshot; no new decision ID or order is created for review. See [current two-role contract](decision-review.md). Earlier single-call verification remains historical evidence.
