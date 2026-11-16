# Curated Part 4.1 evidence

Only selected evidence is included; this is not a full chat export. Market observations shown are public AAPL fields. Credentials are excluded. Local runtime databases remain ignored.

| Intent / prompt | Resulting implementation | Observation | Decision and uncertainty |
|---|---|---|---|
| Prompt05: subscribe to Yahoo; distinguish connection from receipt | backend/feed_probe.py | Initial SSLCertVerificationError; subsequent actual AAPL356.07 update with1.802194s source-to-receipt difference | Use installed certifi trust bundle, keep TLS verification enabled. Socket alone does not prove fresh data. See feed-investigation.md. |
| Prompt06: retain source and receipt evidence; exact repeats vs changed values | backend/recorder.py, docs/sqlite-schema.md | Constructed repeated message yields2 observations/3 deliveries; restart retains rows | Deduplicate exact payload for calculation, retain every delivery. Do not infer correction from timestamp alone. |
| Prompt07: source-ordered minute candles and late arrivals | backend/candles.py, backend/test_candles.py | Constructed cumulative1000→1004→1009→1011 gives volume11; late middle preserves11; reset/missing baseline unknown | Never add cumulative totals as per-event shares. Live semantics remain unverified. |
| Prompt08: follow actual quote from database to chart; disconnect upstream | backend/live.py, backend/main.py, frontend/src/CandleChart.vue | Live record197/receipt199, price356.24, matches14:31 candle; upstream disconnected while browser WebSocket remained open | Persist before broadcast; display independent transport/freshness states. Screenshot is historical live evidence, not a new audit-time capture. |
| Prompt09: replay original arrival order without changing recording | backend/replay.py, backend/test_replay.py | Two browser replays give356.24/Unknown volume;197observations/199deliveries and database hash unchanged | Replay keeps original timestamps and labels. Real capture has no explicit revisions; revision scenarios use constructed fixtures. |
| Submission audit | report.md, part-4.1-checklist.md, AI-USE.md |32focused tests and build pass; read-only SQLite verifies trace197 | Do not mark ready while live volume, repo/commit/video/access and clean checkout remain unresolved. |

Evidence files: [live trace](evidence/live-yahoo-candle-trace.json), [chart](evidence/live-yahoo-trace.png), [disconnected state](evidence/upstream-disconnected.png), [replay comparison](evidence/replay-check.json), [aggregation examples](evidence/candle-aggregation.json), [recorder verification](evidence/recorder-test.json). Full commands and historical failures are in [verification.md](verification.md).

Student explanation to prepare: trace `LiveFeed.receive`/callback → `recorder.record` transaction → Python aggregation → FastAPI stream → Vue reconciliation; explain why a same-time changed payload is retained, why late data can change a completed interval, and why Unknown volume cannot honestly be shown as zero. Confirm exact callback names in live.py while reviewing the source.
