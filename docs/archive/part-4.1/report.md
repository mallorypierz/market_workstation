# Assignment 4.1 — Market Data and the Dashboard

- **Repository:** [market_workstation](https://github.com/mallorypierz/market_workstation) (public).
- **Submitted code and evidence:** [72953e37d4ad8b4b15a835c285bdff38850b4c0e](https://github.com/mallorypierz/market_workstation/commit/72953e37d4ad8b4b15a835c285bdff38850b4c0e). This report is recorded in a subsequent documentation commit.
- **Selected video (1 minute52.08seconds):** [Watch or download my recording](https://raw.githubusercontent.com/mallorypierz/market_workstation/0b479854ef607d5611b9c9405548d2edc06fc7ab/docs/evidence/part-4.1-student-demo.mov). [GitHub video page](https://github.com/mallorypierz/market_workstation/blob/0b479854ef607d5611b9c9405548d2edc06fc7ab/docs/evidence/part-4.1-student-demo.mov).

**Video length requirement remains unmet:** this user-selected recording is112.08seconds; the assignment permits30–60seconds. Shorten it before submission.

This recording replaces the earlier46.44second demonstration. Sampled frames show the AAPL dashboard, disconnected Yahoo with the browser still connected, SQLite record221/receipt223 matching price353.97, and Replay. That record's daily cumulative volume is unavailable. These observations do not establish exact minute volume or a completed replay; earlier live evidence remains linked below.

## Completed work

Vue and TradingView Lightweight Charts display AAPL candlesticks and volume. Python calculates candles; FastAPI transports history and WebSocket updates; SQLite retains decoded source observations, delivery times and revision history. The dashboard exposes source, source/receipt timestamps, age, feed status and candle completion. Stored data can be retrieved and replayed with Yahoo disconnected.

The retained live capture contains **197 distinct observations and 199 deliveries**. On November 12, 2026, observation 197 / receipt 199 carried price **356.24**, source time **14:31:03 UTC**, and receipt time **14:31:10.259674 UTC**. The displayed 14:31 candle matched that closing price. Earlier WebSocket frames show the 14:30 candle changing from close 357.79 to 358.054. Disconnecting Yahoo changed the upstream status while the browser–FastAPI connection stayed open.

Evidence: [source → database → WebSocket trace](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/live-yahoo-candle-trace.json), [live chart](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/live-yahoo-trace.png), [forming candle](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/live-forming-candle.png), and [disconnected upstream](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/upstream-disconnected.png). These describe the historical capture, not today's availability.

## Design decisions

- **Identity and revisions:** canonical exact repeats reuse one observation ID while each delivery retains its receipt ID. Changed same-time messages remain distinct unless explicit correction evidence links them. Original payloads remain available. Yahoo has no verified stable event ID or revision sequence in this capture.
- **Ordering and replay:** source time assigns half-open UTC minute intervals and orders prices, with local observation ID breaking ties. Receipt order determines what replay knows. Late arrivals and identifiable corrections recompute candles without erasing earlier evidence.
- **Completion:** interval end, coverage and completion live outside the six candle fields. An ended candle does not guarantee every exchange event was received.
- **Volume:** Yahoo AAPL day_volume is interpreted as a daily cumulative share counter. Differences are labeled **estimated**, never summed as event volume. The recorded totals 1,958,108 at 14:30:56 and 2,011,028 at 14:31:03 produce **52,920 estimated shares** for the latter minute. That seven-second difference crosses a boundary and does not establish exact minute volume. Missing baselines, resets and ambiguous timestamps remain Unknown. last_size is not substituted.
- **Recovery:** accepted observations persist before broadcast; authoritative snapshots restore browser state after reconnect. Socket connection, source freshness and market-session status remain distinct.

See [data flow](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/design-pipeline.md), [SQLite schema](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/sqlite-schema.md), [aggregation rules](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/candle-aggregation.md), [feed investigation and references](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/feed-investigation.md), and [replay](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/replay.md).

## Verification and revised approach

- **90 backend tests passed**, including duplicate delivery, revisions, late arrivals, restart persistence, retrieval ordering, boundaries, counter resets and disconnected-feed behavior.
- **Frontend build passed.** Chromium displayed the stored 14:31 close 356.24 and **52,920 shares (estimated)**. [Screenshot](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/volume-estimate.png).
- **Full offline browser SmokeTest passed** against isolated SQLite and stubbed external services. It runs the real Vue/FastAPI/chart/database path. [Result](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/submission-smoke.json). This is deterministic verification, not live-feed proof.
- Earlier actual-session replay ran twice with unchanged database counts/hash. Its volume was Unknown under the earlier implementation. [Historical replay check](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/replay-check.json).
- A new 30-second Yahoo probe on November 16 opened a socket and subscribed but received **no observation**. Receipt remains unverified. [Actual probe output](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/evidence/submission-feed-probe.jsonl).

A revised approach addressed volume: the initial implementation withheld all live volume because semantics were unverified. Inspection of retained daily counters supported conservative differencing, so [the aggregation code](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/backend/candles.py) now exposes labeled estimates with baseline/reset guards and [regression tests](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/backend/test_candles.py). It does not replace missing evidence with zero. An earlier TLS failure was fixed using the installed certifi trust bundle without disabling certificate verification. [Commands, failures and results](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/docs/verification.md).

## Setup and remaining limitations

[README](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/README.md) documents initialization (`python3 -m backend.recorder init`), configurable database paths, localhost start/stop commands and `python3 docs/smoke_test.py`. Credentials, environments and runtime databases are excluded from Git. Part 4.1 needs no model API key or Yahoo login. [AGENTS.md](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/AGENTS.md) records project conventions; [AI-USE.md](https://github.com/mallorypierz/market_workstation/blob/72953e37d4ad8b4b15a835c285bdff38850b4c0e/AI-USE.md) discloses the coding assistance and the limits of known model history.

Sparse Yahoo quotes cannot guarantee exchange-complete OHLC or exact minute volume. Some volume remains Unknown. Same-time ordering is locally deterministic; late data can revise ended candles. This short capture is limited to AAPL. The selected recording is over the permitted duration and must be shortened. A fresh regular-session live demonstration would strengthen the live-volume evidence. Later-part indicators, trading and AI/audio features are present but are outside this report's Part 4.1 claims.

**Canvas submission:** upload only this `report.md`. Source code and the video are linked in the public repository; do not upload a source ZIP.
