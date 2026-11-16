# Assignment 4.1 — Market Data and the Dashboard

**Draft — not ready to upload.** The video and live-volume requirement remain unresolved. Supporting links below are pinned to the committed code snapshot.

- **Repository:** [mallorypierz/market_workstation](https://github.com/mallorypierz/market_workstation) — confirmed by the student.
- **Submitted commit:** [370948b7366ba13d0023fe222f1c631dbc6d2e37](https://github.com/mallorypierz/market_workstation/commit/370948b7366ba13d0023fe222f1c631dbc6d2e37) (code snapshot; this report is finalized in a subsequent documentation commit).
- **30–60 second demonstration video:** PENDING — accessible video link and duration not supplied.
- **Remaining feature gap:** corresponding numeric live minute volume is unverified; the live chart correctly reports Unknown. This requirement is not claimed complete.

## Completed work

The local application uses Vue and TradingView Lightweight Charts for presentation, Python for calculations, FastAPI for HTTP and WebSocket transport, and SQLite for durable observations. It streams AAPL updates from Yahoo Finance through yfinance, commits each accepted observation before exposing its derived candle, and reconciles the chart by candle timestamp. The interface shows source, source/receipt timestamps, source age, browser connection, upstream feed status, and candle completion. Stored history and replay remain available while Yahoo is disconnected.

The retained live capture contains **197 distinct observations and 199 deliveries**. On November12,2026, observation197/receipt199 carried AAPL price **356.24**, source time **14:31:03 UTC** and receipt time **14:31:10.259674 UTC**. The browser displayed the14:31 candle with close356.24. Earlier WebSocket frames show the14:30 candle updating from close357.79 to358.054. Upstream disconnection changed the visible feed status while the browser–FastAPI WebSocket remained connected. These are retained live observations, not synthetic CSV data or a new live check performed during this audit.

Evidence: [live source/storage/WebSocket trace](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/live-yahoo-candle-trace.json), [live chart](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/live-yahoo-trace.png), [forming candle](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/live-forming-candle.png), [upstream disconnected](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/upstream-disconnected.png).

## Design decisions

- **Identity and history:** exact canonical payload repeats reuse an observation ID but receive separate delivery IDs. A changed same-time message remains a separate observation unless explicit correction evidence establishes a revision. Original payloads and revision links are retained. Yahoo has not provided a verified stable event ID or revision sequence; local IDs are not exchange sequence numbers.
- **Time and ordering:** source time assigns UTC half-open one-minute intervals. Prices are ordered by source time and then local observation ID for a deterministic tie-break. Receipt IDs preserve arrival order and reconstruct what replay knew at each step. Late observations and evidenced corrections can revise ended candles without deleting earlier evidence.
- **Completion:** completion/coverage metadata is separate from the six candle fields. It is derived from interval boundaries and the selected receipt history; an ended interval is not a guarantee that all market events were received.
- **Volume:** cumulative totals are never summed as per-event volume. The aggregation tests validate differencing only under explicitly supplied cumulative semantics. Live AAPL payloads sometimes contain day_volume/last_size, but their use for reliable minute volume is not verified. Live volume is null/Unknown, not zero. Synthetic bars establish rendering only.
- **Recovery:** the backend sends authoritative candle/status snapshots so reconnecting browsers recover stored state. Replay reads a fixed receipt selection without modifying the capture. Socket connectivity, source freshness and market-session state are distinct.

Supporting design: [data flow/file responsibilities](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/design-pipeline.md), [SQLite schema](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/sqlite-schema.md), [candle rules](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/candle-aggregation.md), [feed investigation](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/feed-investigation.md), [replay](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/replay.md).

## Verification

At the November15,2026 readiness audit:

- `python3 -m unittest backend.test_recorder backend.test_candles backend.test_timeframes backend.test_live backend.test_replay backend.test_history -q`: **32 tests passed**. Coverage includes exact duplicates, identifiable revisions, ambiguous same-time changes, out-of-order arrivals, persistence/reopen, retrieval/replay ordering, interval boundaries, cumulative resets and unavailable/disconnected transport behavior.
- `npm --prefix frontend run build`: **passed**.
- Read-only inspection confirmed the retained197-observation/199-delivery live capture and the price/source timestamp of observation197. Zero revision links exist in this live capture; revision behavior is verified with explicitly constructed tests, not claimed as a witnessed Yahoo correction.
- Earlier actual-capture browser replay ran twice: close356.24, volumeUnknown, unchanged observation/delivery counts and database hash. [Replay comparison](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/replay-check.json).
- The full offline browser SmokeTest passed twice on fresh databases. It exercises the real Vue/FastAPI/chart/SQLite path with deterministic events and stubbed external services; it does not replace live Yahoo evidence. [SmokeTest results](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/evidence/smoke-runs.json).

A failed approach informed the implementation: Python's default TLS configuration initially rejected the Yahoo connection. The probe recorded an unopened socket and unverified receipt. Selecting the installed certifi CA bundle restored verified TLS without disabling certificate verification. The report distinguishes that failure, the later received data, and still-unknown volume semantics. [Curated evidence and relevant code](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/docs/part-4.1-evidence.md).

## Reproduction and limitations

[README](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/README.md) documents database initialization (`python3 -m backend.recorder init`), configurable MARKET_DB_PATH, localhost backend/frontend startup, stop commands, and checks. Runtime databases, environments and credentials are excluded from Git. No Yahoo login or model API key is required for Part4.1. [Agent instructions](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/AGENTS.md) and [AI-use disclosure](https://github.com/mallorypierz/market_workstation/blob/370948b7366ba13d0023fe222f1c631dbc6d2e37/AI-USE.md) record the working procedure.

Current limitations: numeric live minute volume is unresolved; sparse quote updates do not establish exchange-complete OHLC/volume; same-time ordering is locally deterministic rather than provider-sequenced; late data may revise ended bars; AAPL regular-session coverage is limited to the captured window; replay is not a new live observation. Video publication/access and resolution of the live-volume requirement remain pending. A clean tracked checkout of the code SHA passed32focused tests, the build and the full browser SmokeTest, reusing installed Python/npm dependencies; GitHub Actions also passed fresh dependency installation and both offline SmokeTest runs. Later-part indicators, paper trading, model decisions and voice are present but are outside the claims of this Part4.1 report.

**Submission:** upload only the finalized `report.md`, not source files or ZIP archives. The final report must contain the actual repository URL, submitted commit and one accessible30–60second video link. Do not upload this draft with pending fields.

Repository publication: origin/main was pushed without rewriting prior history. The repository is public. [Code-version CI run](https://github.com/mallorypierz/market_workstation/actions/runs/43795770082) passed fresh dependency installation and both offline SmokeTest runs on a GitHub-hosted runner. This verifies offline reproducibility, not live volume.
