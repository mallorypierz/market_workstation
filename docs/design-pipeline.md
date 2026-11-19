# Design pipeline and file responsibilities

Current implementation: local Yahoo subscription -> SQLite -> Python aggregation -> FastAPI HTTP/WebSocket -> Vue candlesticks. Synthetic CSV is an explicitly selectable practice source. Read [live-dashboard.md](live-dashboard.md) for the pre-edit trace, protocol and limitations.

```text
Yahoo AAPL -> yfinance.AsyncWebSocket -> LiveFeed.accept(message)
                                      capture receipt UTC
                                      recorder.record -> SQLite COMMIT
                                                        |
               history_view(source, symbol, timeframe, displayed time)
                                |                       |
                   CSV final minute rows       SQLite unique observations
                                |              + receipt/revision cutoffs
                                |                       |
                                |              Python one-minute aggregate
                                +-----------+-----------+
                                            |
                                 calendar-aware timeframe reduction
                                            |
                        GET /api/history / WS /api/stream snapshots
                                            |
                           Vite /api HTTP + WebSocket forwarding
                                            |
                           Vue timeframe/source selection, chart
                           aligned volume + independent feed status
```

SQLite preserves source fields, duplicates as separate deliveries and explicit correction links. Candle objects always contain timestamp/open/high/low/close/volume. Completion, coverage, feed, symbol and interval metadata remain outside them. Same-time updates and older corrections are reconciled by timestamp in the chart; no calculations move to Vue.

| File | Responsibility |
| --- | --- |
| backend/live.py | Managed AAPL subscription, commit-first callback, bounded retries and upstream/freshness/session state. |
| backend/feed_probe.py | Standalone bounded diagnostic using the same yfinance client and recorder. |
| backend/recorder.py | SQLite initialization, append-only observations/deliveries/revision evidence, snapshots. |
| backend/candles.py | Source-ordered one-minute derivation and known-at receipt filtering. |
| backend/timeframes.py | History source selection and regular-session 1m/5m/15m/1h/1d reduction. |
| backend/history.py | Supplied synthetic CSV reader. |
| backend/main.py | FastAPI lifespan, health/history, WebSocket and local upstream connect/disconnect controls. |
| backend/test_*.py | Constructed data, persistence, aggregation, replay, callback and transport tests. |
| frontend/src/CandleChart.vue | History/stream lifecycle, generation-safe selection, UTC chart, inspection, status and upstream control. |
| frontend/src/chartAdapter.js | Shared time conversion, input checks and own-open direction colors; unknown volume preserved. |
| frontend/vite.config.js | Localhost dev server, HTTP and WebSocket proxy. |
| README.md / AGENTS.md | Purpose, startup, project conventions and dependency approval. |
| docs/verification.md / docs/evidence/ | Commands, outcomes, screenshots, actual observations and clearly labeled constructed evidence. |
| docs/live-dashboard.md | Trace and live transport design. |
| docs/sqlite-schema.md / candle-aggregation.md / timeframes.md | Persistence and calculation rules. |
| prompts/ | Preserved numbered user prompts; prompts 08 and 09 reused for live/replay tasks. |
| handoffs/ | Session ending/resuming instructions and current state. |

Original live_market_workstation folder and ZIP are preserved. No credentials or runtime databases belong in Git. Runtime database is ignored. Single-worker/local-process scope; complete live volume semantics and scalable streaming fanout remain limitations.

## Offline replay (implemented)

`backend/replay.py` reads saved Yahoo deliveries in original receipt-ID order through a read-only SQLite connection. `/api/recordings` lists saved ranges; `/api/replay` delivers the existing minute/timeframe calculation at a fixed receipt ceiling. `frontend/src/CandleChart.vue` provides Replay selection, stepping, pause/restart, original timestamps and explicit empty state. No replay receipts are written back. `backend/test_replay.py` verifies late updates, identified corrections, duplicate delivery, receipt clock regression and repeatability. See [replay design](replay.md).

```text
SQLite -> read-only selected receipt prefix -> Python candles/timeframes
       -> FastAPI /api/replay -> Vue Replay chart
Yahoo disconnected; source times unchanged; no writes back to the capture
```

## Two-SMA extension (2026-11-15)

Selected SQLite receipt prefix / CSV / live observations → existing candle aggregation and completion metadata → `backend/sma.py` exact completed-close calculation → HTTP history, replay or WebSocket `sma` metadata → Vue two line series and confirmed markers. No SMA calculation moves to Vue. `backend/test_sma.py` compares batch and replay, revisions, warm-up, completion and precision; [SMA design](sma.md) defines semantics. Reused supplied prompt 09a.

## Named indicator extension

`backend/indicators.py` owns the rolling scalar registry, catalog, validated window and completed-candle calculations. Existing paired SMA delegates to it. `backend/indicator_store.py` persists independent named settings in a separate SQLite file. FastAPI discovers types and creates/lists instances; history/replay/WS views calculate instances on the selected candle view. Vue dynamically plots each returned series and shows selected-time values. [Contract and schema](indicators.md); `backend/test_indicators.py` checks range, SMA reuse, persistence and replay corrections. Prompt 09b reused.

```text
Vue type/name/window -> FastAPI validation -> chart-settings.sqlite3
Selected candle view + saved per-chart settings -> Python registry
    -> named timestamped values -> Vue lines and inspector table
Market-session SQLite stays separate from configuration writes
```

## Local paper execution extension

Vue PaperAccount controls → FastAPI `/api/paper/actions` → shared `backend.paper.execute` → pending/rejected order and stable request receipt in MARKET_DB_PATH. Existing Yahoo receiver commits observation first, then `paper.process_live` matches pending orders. Fill + cash + position + status + cursor commit in one SQLite transaction. Polling recovers missed post-submission arrivals after restart. Replay uses an independent account and explicit POST advancement over only revealed selected receipts. Market observations/revisions remain unchanged.

`frontend/src/PaperAccount.vue` provides balances/history/retry and replay-account controls; CandleChart passes the displayed replay view. `backend/paper_fixture.py` supplies labeled prices only in disposable fixture paths; `backend/test_paper.py` checks idempotency, rollback, rechecks, restart and no-future-price replay. Reused prompt09c. See [fill rules, API and storage](paper-account.md).

## P&L extension

Persisted fills + revealed observations → `backend/pnl.py` exact weighted-average ledger and completed 1m valuations → append-only `paper_pnl` in MARKET_DB_PATH → existing account HTTP response (`pnl_history`, `pnl_current`) → Vue P&L table. Fill history writes share the execution transaction; replay valuation sees only revealed receipts. `backend/pnl_fixture.py` and `backend/test_pnl.py` verify the reference ledger, precision, deduplication, rollback, restart, unavailable prices and replay. [Rules and schema](pnl.md). Prompt09d reused.

## Frozen decision proposals

```text
Recorded receipt prefix at candle close + known revision links
    -> existing Python minute/timeframe candles + exact SMA crossover logic
Paper starting cash + fills known at that close -> historical account facts
    -> decisions.create_snapshot -> immutable decision_snapshots (ID + digest)
    -> GET saved snapshot.chart (renderable without any model call)
Snapshot ID -> POST /api/decisions -> Python -> OpenAI named choice
    -> backend validation + factual explanation -> decisions row -> caller
No arrow leads to paper.execute; account/market tables remain untouched.
```

New backend/decisions.py owns snapshots, transport, validation and persistence. backend/decision_fixture.py supplies labeled data; backend/decision_check.py compares saved results/ledger; backend/test_decisions.py verifies causality, statuses, HTTP contracts and replay boundaries. paper.py now provides the default proposal size and records initial replay-step provenance. Prompt10 reused. See [contract and checks](decisions.md).

## Chart-image analysis

Vue selected candle + visible range + paper account → immutable decision snapshot → independent Lightweight Charts rendering from saved candles/volume/SMA/named indicators → takeScreenshot PNG with snapshot binding → frozen preview and questions → POST /api/decisions → Python PNG decoder and snapshot validation → one OpenAI user message with input_json and input_image → three named answers → Python crossover/account checks → SQLite decision_images + decisions → Vue result table. Live chart updates cannot change saved capture records. No path submits a paper order.

New frontend AskChart.vue/chartCapture.js own preview/export only; backend/chart_analysis.py owns image validation, questions and result validation. chart_smoke.py starts isolated controlled-provider services; chart_check.py compares image bytes and ledger, optionally performs one live test. Prompt10a reused. [Full design](chart-analysis.md).

## Separate analyst and reviewer

POST decisions → decision_review.run → existing analyst path/client → persisted analyst result under the original ID → separate reviewer call with same snapshot/image plus actual analyst choice/named answers and Python facts → final deterministic gate → same SQLite result. Review pending is never eligible; missing analyst output skips reviewer. The role trace is returned by the same POST/GET API. backend/decision_review.py owns orchestration and policy; review_check.py and test_decision_review.py verify two-call bounds, fixed cases, provenance and ledger immutability. [Review contract](decision-review.md). Prompt11 reused.

## Reviewed paper automation (authorized later-part extension)

Completed WebSocket candle → persistent unique automation job → saved cutoff snapshot → Vue `captureChart` PNG → existing analyst/reviewer service → Python gate → `paper.execute` pending order → next accepted observation → guarded atomic fill/cash/position/P&L/decision linkage → Vue execution trace. Stop and restart invalidate control generations. See [execution rules and SmokeTest](paper-automation.md).

## Read-only voice (authorized later-part extension)

Selected saved decision ID → FastAPI read-only SQLite snapshot of proposal/reviewer/Python gate/linked paper outcome → server-owned GPT-Live session configuration. Browser microphone + WebRTC offer → FastAPI → OpenAI `/v1/live/sessions` → SDP answer → browser peer connection. Microphone and speaker audio use WebRTC tracks; captions use the event channel. Voice has no order/ledger mutation path. Context freezes at voice startup; missing evidence stays missing. See [voice design and checks](decision-voice.md).

## Offline browser SmokeTest

`docs/smoke_test.py` creates fresh temporary market/settings SQLite files → starts `backend.smoke_fixture:app` and real Vite → waits for both → invokes pinned Playwright/Chromium → operates Vue replay/indicator/capture/automation controls → validates provider-bound PNG pixels/identity → checks the production simulator in UI and SQLite → closes browser/process groups and writes ignored evidence. Only source events, logical time and external model/feed boundaries are controlled; calculation/transport/review/execution paths are real. `.github/workflows/smoke-test.yml` invokes the same command twice on push. Details: [SmokeTest](smoke-test.md).


## Part 4.2 audit boundary — November 17, 2026

The [readiness checklist](part-4.2-checklist.md) distinguishes existing calculations/accounting from planned strategy/backtest orchestration. Current automatic execution runs through chart-image analyst/reviewer calls and the Python gate. Manual paper actions and replay accounts can operate without a model, but no provider-independent automatic crossover runner or historical performance-run API/UI was found. Proposed flow: receipt-bounded history → completed candles → existing SMA → deterministic strategy → existing paper ledger → persisted run results → Vue. This flow is a plan only; this audit changes no runtime behavior or schema.


## Deterministic SMA strategy — implemented November 17, 2026

The earlier audit gap for provider-independent forward strategy execution is now closed. Yahoo recorder → existing `paper.process_live` transaction → each enabled run's receipt cursor → known-at completed candles → exact SMA → buy-one/close/no-action event → shared pending paper order → strictly later eligible receipt → shared fill/P&L → FastAPI strategy state → Vue SmaStrategy. Runs use isolated `strategy-` accounts and immutable settings. Stop serializes with processing and cancels pending orders. The existing AI-reviewed and manual replay paths remain separate. [Rules, schema, limitations and verification commands](sma-strategy.md). Historical backtesting/performance reporting remains unimplemented.


Part4.2 accounting verification uses disposable fixtures → existing paper/P&L pipeline → direct SQLite query → FastAPI account JSON → Vue P&L table, then repeats after actual backend restart. [Reconciliation](pnl.md) supplies independent expected amounts/equity identities. No accounting formula or runtime schema changed; the only presentation change keeps monetary cells on one line.


## Historical backtest — implemented November 17, 2026

Read-only source snapshot or explicitly labeled daily bars → frozen input/config/hash in isolated run SQLite → sequential receipt or open/close availability → shared exact SMA + choose_action → shared paper execution/P&L → frozen decision/fill/valuation audit → persisted equity/return/drawdown results → CLI/FastAPI. The daily adapter exposes the close only after the session ends and executes earlier orders only at the next supplied open. No pre-period warm-up trades, production account writes or forced liquidation. [Rules and evaluation](backtesting.md). Dedicated Vue backtest controls/results are still pending.

Part4.2 backtest UI: dataset catalog → validated Vue form → strict FastAPI request → frozen isolated Python evaluation → SQLite result → saved-result GET → candle/SMA/marker and equity charts plus frozen decision/order/fill inspection. Refresh/restart reads persisted results. Source captures and live paper account remain separate. See docs/backtesting.md for empty/unavailable states and browser evidence.

Submission evidence boundary: constructed correctness receipts → isolated deterministic strategy/backtest → SQLite/browser assertions is separate from saved real Yahoo daily-bar evaluation and earlier Part4.1 live captures. The59-second recording shows actual saved app results with narration captions, not a fresh live-feed claim. The report documents receipt-prefix causality, next-open historical execution, no parameter optimization, survivorship/selection bias and the small one-symbol sample. See part-4.2-evidence.md for observed checks and pending publication.
