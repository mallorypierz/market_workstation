# Market Workstation

## Project overview and goals

A local market-data dashboard for the student's Assignment 4, Part 4.1. The student will use it to follow live Yahoo Finance prices and volume, understand source freshness and feed failures, and retrieve/replay persisted observations. The instructor will review the working application and its evidence.

Goals: updating candlesticks with aligned volume; visible source, source/receipt times, age and feed state; WebSocket delivery; SQLite records preserving identity, revisions and completion; deterministic duplicate/out-of-order handling; replay for development when live data is unavailable. CSV loading is ungraded practice. Indicators, trading, backtesting, AI, and audio are outside this setup/Part 4.1 scope.

## Agreed root and stack

Project root: `/Users/mallorypierz/Documents/market_workstation`. Reuse this folder and preserve existing work.

- Python: backend logic, normalization, calculations and future persistence.
- FastAPI: HTTP/WebSocket transport carrying requests and results between Python and Vue.
- Vue: user input, components, chart presentation and status displays.
- SQLite: append-only decoded observation, delivery and explicit revision records using Python's built-in support.

Implemented: a minimal Vue interface, a Vite `/api` proxy, FastAPI health and synthetic CSV history endpoints. The frontend displays synthetic one-minute candlesticks and aligned volume using TradingView Lightweight Charts. A separate bounded Yahoo subscription probe has received an AAPL update. The receiver records accepted messages in SQLite. FastAPI now manages the AAPL subscription and sends Python-derived candles/status over WebSocket to Vue, with one-minute default and selectable larger timeframes.

## Prerequisites found on this computer

Checked 2026-11-11: macOS 26.5.2 (ARM64); Python 3.12.5; pip 24.2; Node.js v24.20.0; npm 11.19.0; built-in SQLite 3.45.3. Selected Python interpreter: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`. No active virtual environment; the prior project environment was deleted. Reuse the available interpreter for checks, without creating a new venv by default.

Approved and installed: FastAPI 0.162.0 and Uvicorn 0.54.0 in the existing Python user site; Vue 3.5.45, Vite 8.3.6 and @vitejs/plugin-vue 6.0.10 in frontend-local npm dependencies. Direct Python dependencies are pinned in `backend/requirements.txt`; npm dependencies are pinned and locked in `frontend/package.json` and `frontend/package-lock.json`. Lightweight Charts 5.3.0 is now installed locally after approval; yfinance 1.8.0, websockets 17.4 and exchange-calendars 4.13.2 are installed in the Python user site after approval. Before future dependency work, follow CHECK → TAKE ACTION → VERIFY in [AGENTS.md](AGENTS.md), with student approval for installations and manifest/lockfile changes.

## Setup and run instructions

Run the complete offline browser SmokeTest from the project root:

```sh
python3 docs/smoke_test.py
```

Run these tested commands in two terminals from the project root:

```sh
SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')" python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
```

```sh
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173/ and click **Check backend**; expect `{"status":"ok"}`. Stop either foreground service with **Ctrl+C** in its terminal (tested); restart with the same command. Only bind to localhost. Vite's proxy is a development feature; the production build alone does not provide this proxy.

```sh
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:5173/api/health
curl -i http://127.0.0.1:8000/api/history
python3 -m unittest backend.test_history -v
npm --prefix frontend run build
node --test frontend/src/chartAdapter.test.js
```

For approved dependency restoration, the declarations are `backend/requirements.txt` and `frontend/package-lock.json`. Follow AGENTS before installation on another machine; fresh-checkout installation has not been tested. Git is not initialized; no commit or remote operation was performed.

## Synthetic history contract

`GET /api/history` reads the supplied `prompts/data/sample-candles.csv` using Python's built-in `csv` module. It returns an ascending UTC JSON array with exactly `timestamp, open, high, low, close, volume`. The `X-Data-Source: synthetic-csv` header and frontend label identify practice data. No extra JSON fields are added. Missing or invalid files return HTTP 503.

Each row is one instrument's one-minute candle; the instrument is unspecified by this six-field fixture. UTC timestamps mark inclusive starts and exclusive next-minute boundaries. Volume is shares traded during that minute, not cumulative volume. Prices are JSON numbers. Duplicate minute rows and invalid timestamps/OHLC/volume are rejected rather than silently merged. File paths resolve relative to the project, independent of the launch directory.

These same one-minute rows now provide on-request 5-minute, 15-minute, hourly and daily history. The synthetic SAMPLE instrument uses the XNAS regular-session calendar for this exercise; it remains anonymous practice data. Daily timestamps mark session opens, not UTC midnight. See [timeframe rules](docs/timeframes.md).

## Source folder map (generated dependencies/build caches omitted)

```text
market_workstation/
|-- backend/
|   |-- voice.py
|   |-- test_voice.py
|   |-- automation.py
|   |-- automation_smoke.py
|   |-- smoke_fixture.py
|   |-- test_automation.py
|   |-- chart_analysis.py
|   |-- chart_smoke.py
|   |-- chart_check.py
|   |-- test_chart_analysis.py
|   |-- decision_review.py
|   |-- review_check.py
|   |-- test_decision_review.py
|   |-- decisions.py
|   |-- decision_fixture.py
|   |-- decision_check.py
|   |-- test_decisions.py
|   |-- pnl.py
|   |-- pnl_fixture.py
|   |-- test_pnl.py
|   |-- paper.py
|   |-- paper_fixture.py
|   |-- test_paper.py
|   |-- indicators.py
|   |-- indicator_store.py
|   |-- test_indicators.py
|   |-- sma.py
|   |-- test_sma.py
|   |-- replay.py
|   |-- test_replay.py
|   |-- live.py
|   |-- test_live.py
|   |-- timeframes.py
|   |-- test_timeframes.py
|   |-- candles.py
|   |-- test_candles.py
|   |-- feed_probe.py
|   |-- history.py
|   |-- main.py
|   |-- recorder.py
|   |-- test_recorder.py
|   |-- requirements.txt
|   `-- test_history.py
|-- docs/
|   |-- evidence/ (connection.png, sample-chart.png, yahoo-aapl-probe.json)
|   |-- decision-voice.md
|   |-- paper-automation.md
|   |-- chart-analysis.md
|   |-- decision-review.md
|   |-- decisions.md
|   |-- pnl.md
|   |-- paper-account.md
|   |-- indicators.md
|   |-- sma.md
|   |-- replay.md
|   |-- live-dashboard.md
|   |-- timeframes.md
|   |-- candle-aggregation.md
|   |-- feed-investigation.md
|   |-- design-pipeline.md
|   |-- sqlite-schema.md
|   |-- smoke_test.py
|   |-- structure_check.py
|   |-- smoke-test.md
|   `-- verification.md
|-- frontend/
|   |-- index.html
|   |-- package.json
|   |-- package-lock.json
|   |-- vite.config.js
|   |-- smoke.config.js
|   |-- tests/smoke.spec.js
|   `-- src/ (App.vue, main.js, CandleChart.vue, AskChart.vue, PaperAutomation.vue, DecisionVoice.vue, voiceConnection.js, voiceConnection.test.js, chartCapture.js, PaperAccount.vue, chartAdapter.js, chartAdapter.test.js)
|-- handoffs/
|   |-- create-handoff.md
|   `-- current.md
|-- live_market_workstation/
|   |-- prompts/
|   `-- .DS_Store
|-- prompts/
|   |-- data/
|   |-- 01-generic-project-startup.md
|   |-- 02-connect-vue-and-fastapi.md
|   |-- 03-load-historical-csv.md
|   |-- 04-integrate-candlestick-chart.md
|   |-- 05-connect-yahoo-finance.md
|   |-- 06-record-observations-in-sqlite.md
|   |-- 07-form-market-candles.md
|   |-- 07a-derive-higher-timeframes.md
|   |-- 08-display-live-updates.md
|   |-- 09-replay-recorded-observations.md
|   |-- 09a-calculate-moving-averages.md
|   |-- 09b-create-chart-indicators.md
|   |-- 09c-build-paper-trading.md
|   |-- 09d-record-profit-and-loss.md
|   |-- 10-add-decision-api.md
|   |-- 10a-ask-about-chart.md
|   |-- 11-add-agent-review.md
|   |-- 12-apply-reviewed-paper-decision.md
|   |-- 13-add-live-speech.md
|   `-- 14-automate-workstation-smoke-test.md
|-- .DS_Store
|-- .github/workflows/smoke-test.yml
|-- .gitignore
|-- AGENTS.md
|-- README.md
`-- live_market_workstation.zip
```

`prompts/data/` contains the provided `sample-candles.csv` practice fixture. The original starter folder and ZIP remain intact. Root prompts are unchanged copies, retaining their supplied numbering; later-part prompts do not expand current scope. macOS `.DS_Store` files are metadata, not application source.

See [design pipeline](docs/design-pipeline.md), [verification results](docs/verification.md), [handoff instructions](handoffs/create-handoff.md), and [current state](handoffs/current.md).

## Inspect the sample chart

Start both services with the commands above and open http://127.0.0.1:5173/. Select SAMPLE · synthetic CSV and 1 minute to inspect this practice fixture. The chart fetches `/api/history` through Vite. Three separate minutes appear, with share volume beneath the price pane on a shared UTC axis. Hover over a candle or choose **Inspect candle (UTC)**. November 9, 2026 at 14:31 UTC must show open 102, high 104, low 100, close 101 and volume 850 shares. Green means close >= that candle's open; red means close < open, for both series. **Reload sample** rereads backend history; unavailable and empty responses are identified without substituting data.

The adapter converts UTC ISO timestamps to Unix seconds for both series. This is a synthetic one-minute sample, not live data. The single instrument is unspecified by the CSV. TradingView's notice and link appear beneath the chart. See [official chart documentation](https://tradingview.github.io/lightweight-charts/docs) and [browser evidence](docs/evidence/sample-chart.png).

## Bounded Yahoo backend probe

From the project root, reuse the same Python interpreter:

```sh
SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')" python3 -m backend.feed_probe --symbol AAPL --seconds 30
```

The local Python default certificate configuration failed verification; the command selects the certifi trust bundle installed with the approved dependencies and keeps TLS verification enabled. No Yahoo login is required. It exits after one matching update or the timeout; exit 0 means a price observation was received, exit 2 means receipt is unverified. A parent deadline bounds cleanup/import time to an additional 15 seconds. Output distinguishes socket-open, subscription sent, source timestamp, callback receipt timestamp, and any available volume fields. No credentials should be passed to this probe.

The tested run received an AAPL update; no volume field was present. See [field investigation and limitations](docs/feed-investigation.md). The standalone probe remains available; the main app now manages a continuous AAPL receiver and chart WebSocket. Subsequent runs can fail or receive no data; those outcomes must be recorded honestly.

## Initialize and inspect observation storage

From the project root:

```sh
python3 -m backend.recorder init
python3 -m backend.recorder snapshot
python3 -m unittest backend.test_recorder backend.test_history -v
```

Default database: `/Users/mallorypierz/Documents/market_workstation/backend/data/market.sqlite3`. Initialization is idempotent and also runs when the receiver opens the database. For another local path, set `MARKET_DB_PATH` on both initialization and receiver commands. Relative values resolve under this project root. The bounded Yahoo probe now commits accepted observations before printing their stored IDs. Its exit 0 requires successful persistence. SQLite and sidecars are ignored; do not commit runtime data.

Tested disposable initialization (constructed input only):

```sh
MARKET_DB_PATH=/private/tmp/market-recorder-test-qli4h7tk/constructed.sqlite3 python3 -m backend.recorder init
MARKET_DB_PATH=/private/tmp/market-recorder-test-qli4h7tk/constructed.sqlite3 python3 -m backend.recorder snapshot
```

That temporary path may later be removed by the OS. Automated tests allocate their own disposable databases and restart the backend recorder as new Python processes. `record-test` accepts newline-delimited objects containing `payload` and timezone-aware `receipt_time` on stdin, always labeled source `constructed-test`; it should only be used with a disposable database.

An exact repeat reuses the observation ID and adds a delivery receipt. Changed messages are retained separately, even with the same source time; Yahoo has not supplied evidence allowing a correction to be inferred. Explicitly identified revisions retain both values and an evidence link. Query each observation_id once to avoid counting repeat deliveries twice; do not sum cumulative day_volume. See [schema and reader rules](docs/sqlite-schema.md) and [verification](docs/verification.md).

## One-minute candles from SQLite

```sh
python3 -m backend.candles --symbol AAPL
python3 -m unittest backend.test_candles backend.test_recorder backend.test_history -v
```

Uses the same configurable MARKET_DB_PATH as the recorder. Output contains a `candles` array of exactly six fields per minute and separate `status` metadata, including `ended`. `--as-of` accepts an aware ISO timestamp; `--receipt-cutoff` limits recorded knowledge. For constructed data with known cumulative totals, add `--source constructed-test --cumulative-volume-field day_volume`. Do not enable that field for Yahoo until its semantics are verified. Unknown volume is null. Read [aggregation rules](docs/candle-aggregation.md) for late data, corrections, completion and estimated-volume limitations. This CLI does not replace the synthetic `/api/history` endpoint or update the Vue chart.

## History timeframe requests

The history endpoint defaults to `symbol=SAMPLE`, `source=sample`, `timeframe=1m`. Request 5m, 15m, 1h or 1d explicitly. For AAPL recorded observations, use `source=yahoo&symbol=AAPL`; no live data is substituted when storage is empty.

```sh
curl 'http://127.0.0.1:8000/api/history?symbol=SAMPLE&timeframe=5m&include_metadata=true'
curl 'http://127.0.0.1:8000/api/history?symbol=SAMPLE&timeframe=1d&include_metadata=true'
curl 'http://127.0.0.1:8000/api/history?symbol=SAMPLE&timeframe=5m&as_of=2026-11-09T14:31:00Z&include_metadata=true'
python3 -m unittest backend.test_timeframes backend.test_candles backend.test_recorder backend.test_history -v
```

Without include_metadata, the response is the compatible array of six-field candles. With it, `candles` contains that array and separate `status` tracks coverage/completion and volume quality. The three sample minutes aggregate to O100 H105 L99 C104 V3550, with only 3/5 five-minute coverage and 3/390 daily coverage. Zero, unknown volume and partial coverage remain distinct. Regular sessions use the calendar's XNAS alias (XNYS rules), including early closes and DST; see [timeframes](docs/timeframes.md) for supported symbols, availability and replay rules. Vue defaults to AAPL one-minute history/live subscription. The source selector explicitly offers the synthetic sample; all supported timeframes are selectable.

## Live dashboard

Start both services with the commands above; use one backend worker and localhost only. AAPL/1 minute is the default. FastAPI starts the existing yfinance subscription automatically, persists accepted messages, and sends authoritative candle/status snapshots over `/api/stream` about once per second. Select 5 minutes, 15 minutes, hourly or daily to load matching backend history and stream. Select SAMPLE only for explicitly labeled synthetic practice data. The chart's date/time inspector shows exact OHLC, unknown/known volume and whether the candle is still forming.

The page displays upstream feed state separately from its FastAPI connection. Use **Disconnect Yahoo feed** while watching the page: Yahoo should become disconnected while Browser → FastAPI remains connected. **Connect Yahoo feed** restarts bounded connection attempts. Source age, source/receipt timestamps and stored record IDs support tracing. If the regular session is closed, Yahoo updates may be stored without producing a regular-session candle; no sample substitution occurs.

To run without starting upstream Yahoo (e.g. deterministic local tests), prefix the backend command with `MARKET_FEED_ENABLED=0`. The feed can then be started explicitly from the local page. Stop both foreground services with Ctrl+C. Read [live dashboard design](docs/live-dashboard.md) for snapshot recovery, status meanings, volume limitations and tests.

```sh
python3 -m unittest backend.test_live backend.test_timeframes backend.test_candles backend.test_recorder backend.test_history -v
node --test frontend/src/chartAdapter.test.js
npm --prefix frontend run build
```

Actual live price-to-chart verification is recorded in [verification.md](docs/verification.md): observation #197 / receipt #199, source 2026-11-12T14:31:03Z at 356.24, produced the 14:31 candle shown in the browser. Upstream disconnection changed feed status while the browser stayed connected; page reload recovered the stored candles. Numeric live minute volume remains unknown. Runtime SQLite contains these public market observations and stays out of Git.

## Replay a saved session with Yahoo off

From the project root, start two terminals:

```sh
MARKET_FEED_ENABLED=0 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173/, choose **Replay**, choose the saved symbol and UTC receipt-time range, then **Load selection** and **Play replay**. **Next observation**, **Pause replay**, and **Restart replay** support inspection. Choose any supported timeframe to restart that selection using backend aggregation. Stop each service with Ctrl+C. Replay uses the existing configurable `MARKET_DB_PATH` (default `backend/data/market.sqlite3`) read-only; no separate initialization is needed for an existing capture. A missing recording produces an explicit empty message. Entering Replay disconnects the shared Yahoo subscription; switching back does not silently reconnect it.

The chart labels Replay and displays each original source/receipt timestamp. The final candle can still be forming at the final recorded receipt. Two browser runs of the actual 199-delivery AAPL capture matched the saved 14:31 UTC close of 356.24; volume remained Unknown. See [replay rules and API](docs/replay.md) and [verification](docs/verification.md).

```sh
python3 -m unittest discover -s backend -p 'test_*.py' -v
node --test frontend/src/chartAdapter.test.js
npm --prefix frontend run build
```

## Two simple moving averages (authorized extension)

Choose **Short SMA** and **Long SMA**, then **Apply SMA windows**. Both must be positive whole numbers and short must be smaller than long. Defaults are 2/3. Python uses completed candles of the selected symbol/timeframe; warm-up, unfinished and incomplete candles show unavailable values. Blue is short, purple is long; green up/red down markers show confirmed changes of side. The inspector and crossover list expose checked values. Ties retain the previous side. Applying new windows restarts replay.

This is an explicitly requested extension beyond the original Part 4.1 scope. See [SMA rules and repeatable checks](docs/sma.md), [reference evidence](docs/evidence/sma-reference.json), and [browser verification](docs/verification.md). No dependency changes. Start/stop commands remain the same.

## Named indicator instances

In **Saved indicators**, choose Simple moving average or Rolling price range, enter a name and a positive whole-number window, and click **Add indicator**. The table shows values at the candle selected by the inspector or crosshair; unavailable means warm-up/incomplete, not zero. Range lines have their own pane. Each named instance keeps its own window.

Settings save automatically to SQLite and return when the same symbol/source/interval is reopened. Default settings file: `backend/data/chart-settings.sqlite3`; override with `MARKET_SETTINGS_DB_PATH`. The first valid save initializes it. Market observations stay in the separate `MARKET_DB_PATH` file. Both are ignored by Git. Refresh defaults to AAPL/1m; select another saved chart's symbol/interval to reopen its instances. Legacy paired-SMA controls are still session-only; named SMA instances use the same calculation interface and are persisted.

See [indicator contract, API, schema and fixture commands](docs/indicators.md). Verification: Range 2=5 and Range 3=6 on the third fixture candle, both survive refresh, zero rejected without losing valid settings. No new packages were needed.

## Local paper account (authorized simulation extension)

The chart now includes a **Paper account · simulated only** panel with cash, shares, order history and linked fills. Default account starts once at $1,000 in the existing MARKET_DB_PATH database. Initialization is automatic on first paper API use and never resets persisted balances. Buy/sell whole shares or close the full position. Hold/wait create no orders. No real broker or real-money trading is connected.

Accepted orders wait for the **next eligible observed price after submission**, with zero fees. Cash/shares are rechecked at fill; prices round to cents. **Retry last request** preserves the same request ID to avoid duplicate orders/fills. In Replay, explicitly start a separate replay paper account; only later revealed receipts may fill its orders. A rewind requires a new account, preserving prior evidence.

Startup/stop commands remain unchanged. To verify with known prices, use the [disposable fixture commands and detailed execution rules](docs/paper-account.md), not the actual captured session. The completed browser check ended at $1,025, zero shares and exactly three persisted fills after a backend restart; [verification evidence](docs/verification.md). No dependencies were added.

## Paper P&L history

The separately authorized paper-account extension now records weighted-average realized/unrealized P&L after fills and completed one-minute candle marks. Vue shows an append-only history, valuation source/time and unavailable values. [Calculation, schema and fixture startup](docs/pnl.md) describe initialization in MARKET_DB_PATH and the tested `python3 -m backend.pnl_fixture` command. No extra packages are required. [Verification](docs/verification.md) compares the five-event example with SQLite and the browser before/after restart.

## Frozen model decisions (proposal-only extension)

Create an immutable snapshot with POST `/api/decision-snapshots`, inspect its saved chart/facts with GET, then POST its snapshot_id to `/api/decisions`. The model proposes buy/sell/hold/wait/close; Python validates against historical cash/shares and the configured order size. No paper order is created and the ledger remains unchanged. Snapshots and results persist in MARKET_DB_PATH; incomplete and test snapshots cannot become eligible orders.

The OpenAI key is read only from backend `OPENAI_API_KEY`. No additional package is needed. `MARKET_PAPER_ORDER_SIZE` defaults to1 and is frozen with each snapshot. [API, statuses, causal rules and secure startup instructions](docs/decisions.md) include the repeatable `python3 -m backend.decision_check` and optional single live-call verification. [Observed checks](docs/verification.md) distinguish a live model call from test market data.

## Ask about chart

Choose a completed AAPL candle, click **Ask about chart**, inspect the frozen chart-only PNG and questions, then **Analyze frozen chart**. The preview stays fixed while live data updates. The three named answers (action, crossover, evidence) appear alongside Python's crossover and validation; analysis creates no orders. Saved PNGs and results remain retrievable by decision ID.

Run `python3 -m backend.chart_smoke` for the isolated supervised browser test. [Capture contract, setup and checks](docs/chart-analysis.md) document the operation and SQLite comparison. The completed student-operated browser test and one live image request both returned buy/up/sufficient on labeled synthetic data; [verification](docs/verification.md) records the browser-tool restriction and initial test-double error honestly. No dependency or lockfile changes were needed. Standard startup is unchanged; optional VITE_API_TARGET selects a different local backend for an isolated test.

## Analyst/reviewer trace

POST `/api/decisions` now makes at most one analyst and one reviewer call on the same saved snapshot (and identical PNG for chart analysis). GET the returned decision ID to inspect both roles' instructions, visible categorical outputs, model names, snapshot digest and final Python checks. Acceptance never overrides cash, position, signal or evidence rules; no order is executed. Complete test data remains execution-ineligible.

[Review policy, trace and statuses](docs/decision-review.md) describe the workflow. Run `python3 -m backend.review_check` for the three controlled cases, or the documented `--live` check once for one two-call example. No dependency installation is needed. Restart the backend to load the new endpoint behavior.

## Reviewed paper automation

The explicitly authorized extension adds **Start paper automation** and **Stop paper automation** to the AAPL chart. Each newly completed candle gets an immutable snapshot, fresh chart PNG, analyst call, reviewer call and Python gate. Accepted orders use the existing next-observed-price simulator. The trace links the decision, order, fill and resulting account state. Manual chart questions still create no orders.

Stop cancels unfilled automated orders and prevents pending replies from executing. A backend restart disables automation; press Start again. Execution expires 120 seconds after candle close by default (`MARKET_DECISION_MAX_AGE_SECONDS`, range 1–3600). Run the normal backend/frontend commands above; stop each with Ctrl+C. Initialization is automatic in the configured `MARKET_DB_PATH`; no new dependencies are needed.

```sh
python3 -m unittest backend.test_automation -v
python3 -m backend.automation_smoke
```

The second command starts a disposable constructed-data test on localhost5174/8010, with no API key. Follow [browser steps and execution rules](docs/paper-automation.md); Ctrl+C stops both services. Evidence is [recorded here](docs/evidence/automation-check.json). This check used controlled provider replies, not a live model or Yahoo stream.

## Read-only decision voice (authorized extension)

The **Discuss a recorded decision by voice** panel lets you select a saved decision, inspect its evidence and start a two-way GPT-Live WebRTC conversation. Backend `OPENAI_API_KEY` is required; no new dependencies are needed. Microphone access starts only when you click Start voice. Voice receives the stored proposal/review and any linked paper outcome; it cannot submit orders. End voice releases the microphone. The panel identifies AI-generated audio, microphone activity and provider/market-data labels.

[Connection design, exact live-check startup commands and verification procedure](docs/decision-voice.md) document the localhost5175/8001 check. Normal startup commands above also serve voice. Audio and the selected summary are sent to OpenAI; credentials stay in the backend environment. Live microphone/speaker verification must be reported separately from mocked transport tests.

Live verification completed: the student heard both answers in one GPT-Live session, confirmed End released the browser microphone, and the answers matched the saved wait/accept/no-fill record. SQLite balances/order counts stayed unchanged. See [observed voice evidence](docs/evidence/voice-selected-record.json). Underlying market observations were constructed, not live market evidence.


## One-command offline browser SmokeTest

```sh
python3 docs/smoke_test.py
```

Starts FastAPI and Vue on isolated localhost ports, opens real Chromium, exercises replay/SMA editing, real chart PNG capture and analyst/reviewer coordination, then executes the deterministic paper-account sequence. Expected final result: **$1,025 cash, zero shares, three fills, $25 realized and $0 unrealized P&L**. The command compares Vue and SQLite, tests veto/duplicate/Stop behavior, returns nonzero on a missing result, and cleans up its browser/processes. A fresh database/account is used every time. No live connections or provider credentials are used.

[Setup, exact assertions, artifacts and failure diagnostics](docs/smoke-test.md). Playwright Test1.65.1/Chromium were installed with approval; normal runs install nothing. [.github/workflows/smoke-test.yml](.github/workflows/smoke-test.yml) runs this same command twice on pushes. Remote CI execution is pending repository setup/push; no Git operations were performed. Prior live Yahoo, image-model and two-way voice checks remain separate in verification.md. The former structure-only check remains `python3 docs/structure_check.py`.

Saved indicator rows now let you edit and save each instance's window. This preserves the indicator ID/name and other instances; changing settings restarts replay so values remain based on the revealed observations.

## Part 4.1 submission audit

[Submission checklist](docs/part-4.1-checklist.md), [draft report](report.md), [curated Part4.1 evidence](docs/part-4.1-evidence.md), and [AI-use disclosure](AI-USE.md) collect the submission material. **Not ready to upload:** live numeric volume remains unverified, and the repository/commit,30–60second video, instructor access and clean-checkout verification are pending. Do not use later-part/offline successes to claim these gaps are resolved. Upload only the finalized report.md after reviewing its links and limitations.

Repository confirmed for submission: https://github.com/mallorypierz/market_workstation . On November15 the student authorized commit/push of the current project. Local main was based on the existing remote commit; five remote-only setup prompts were preserved. Earlier “no Git repository” entries describe historical checks. See report.md for the selected code commit once publication completes. The report remains a draft until the video and live-volume limitation are addressed.

Publication update: code snapshot [370948b7366ba13d0023fe222f1c631dbc6d2e37](https://github.com/mallorypierz/market_workstation/commit/370948b7366ba13d0023fe222f1c631dbc6d2e37) was pushed to the confirmed public repository, preserving its existing history. Report links use this code version; video and verified live-volume evidence are still outstanding. Historical “no Git” or “CI not pushed” notes describe earlier states.

November16 publication verification: [GitHub Actions run43795770082](https://github.com/mallorypierz/market_workstation/actions/runs/43795770082) completed successfully, including fresh dependency installation and two offline SmokeTest runs for code snapshot370948b. Repository/commit and reproducibility checks are now complete. The required video and numeric live-volume verification remain open; report.md is still a submission draft.


Yahoo AAPL volume now uses observed differences of day_volume, labeled **estimated**. Missing baselines, resets and ambiguous updates remain Unknown. See [volume investigation](docs/feed-investigation.md) for the recorded 52,920-share comparison and limitations.
