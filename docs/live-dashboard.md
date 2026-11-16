# Live dashboard transport and status

## Traced inputs and outputs before editing

- frontend/src/CandleChart.vue fetched the synthetic `/api/history` array and mapped UTC ISO minute timestamps to chart Unix seconds. It had no live subscription.
- backend/feed_probe.py used yfinance.AsyncWebSocket to subscribe to AAPL, captured receipt UTC, and committed decoded messages using recorder.record. It stopped after one update or its timeout.
- backend/candles.py aggregate read immutable observations, delivery cutoffs and revision links to calculate current one-minute candles. There was no event-driven candle mutation function: candles were recomputed when aggregate/history_view was called.
- backend/timeframes.py history_view selected that minute view and resampled it using regular-session calendar boundaries. It returned six-field candles and separate completion metadata.

## Implemented path

```text
Yahoo AAPL -> existing yfinance.AsyncWebSocket client in managed LiveFeed
          -> callback receipt UTC -> recorder.record transaction -> COMMIT
          -> latest observation/receipt IDs and source/receipt time published
          -> history_view -> aggregate one-minute -> regular-session resampling
          -> FastAPI /api/stream -> Vite WebSocket proxy -> Vue chart
```

The standalone bounded probe remains available. LiveFeed uses the same subscription client, one-symbol subscription and recorder path for continuous operation under FastAPI's lifespan. One process owns one AAPL upstream connection, independent of browser count. Run one Uvicorn worker for this local app. No new packages or dependency manifests were needed; installed FastAPI, Uvicorn and websockets support the transport.

On each callback, persist before publishing successful record IDs. Every browser stream polls the authoritative backend view once per second, after commits; status/completion therefore updates even without a new trade. This is server-side snapshot sampling delivered over WebSocket, not a promise to render every tick individually. Intermediate messages are retained in SQLite. Recomputing whole views is intentionally simple for this small local project; long-history scalability is a limitation.

## Protocol and recovery

`/api/stream?source=yahoo&symbol=AAPL&timeframe=1m` (or sample/SAMPLE) selects one fixed source/symbol/interval. Unsupported combinations close with code 1008. First message type is snapshot, subsequent type is candle_update. Every message includes an authoritative `candles` array with exactly six fields per candle, `status` keyed by timestamp, source/symbol/timeframe/interval/as_of, feed status, receipt cutoff when available, connection-local sequence, changed `updates` entries containing `candle` and `completion`, and removed timestamps.

Every frame carries the complete selected view, even if only feed status or ended state changed. This makes updates/removals/older corrections recoverable without maintaining an unbounded event queue. Slow sends have a five-second deadline. Reconnect begins with a fresh snapshot; sequence numbers are per connection and are not provider event IDs. SQLite receipt IDs remain the audit sequence.

Vue first requests matching history, then accepts the stream's authoritative snapshot. An update between those steps is included in that snapshot: there is no history/subscription gap to recover manually. Switching source/timeframe aborts old history, closes the old socket and increments a generation token so late old responses cannot contaminate the new chart. A failed browser socket reconnects after two seconds and reconciles by full timestamp view.

Vue replaces series data without refitting the viewport after the first nonempty snapshot. The same timestamp remains one candle; a later interval adds a new timestamp; revised older candles and removed timestamps are reconciled. Price calculations remain in Python. Both series share converted UTC time. Null volume is a chart whitespace point, not a zero bar. Colors use each candle's own close versus open. The inspector shows unknown volume, ended/still forming, and partial coverage independently.

## Feed status is independent of browser transport

Browser -> FastAPI displays connected/connecting/disconnected. Yahoo socket is separately displayed. Feed states include connecting, connected (socket open but no source time yet), receiving (source age 0–30 seconds), stale (older or future timestamp), unavailable (connection failure/retry exhaustion), disconnected (manual stop), and synthetic (explicit sample source). Source age is backend wall clock minus the latest received source timestamp, not time since WebSocket connection. Negative source age is classified stale; the UI clamps its numeric age at zero rather than showing a negative duration. Current latest record and receipt identifiers, source timestamp, receipt timestamp and price are displayed for tracing.

Regular-session open/closed is derived separately from XNAS calendar, not inferred from price arrival or the raw Yahoo market_hours code. Yahoo can send updates outside regular hours; these are stored and shown in latest-source status, but remain excluded from regular-session candles. No synthetic data is silently substituted.

Five connection attempts maximum, with 2/4/8/16 second delays and a 12-second connect/subscribe timeout per attempt. The pinned yfinance transport state is checked twice per second; an internal listener still running does not establish an open upstream socket. Manual connect restarts attempts; manual disconnect cancels the upstream listener and closes Yahoo while retaining browser sockets and stored history. Storage/callback failure reports unavailable instead of publishing an uncommitted update. Cleanup has bounded waits.

Local controls: POST /api/feed/disconnect and POST /api/feed/connect, exposed via the chart's button. They affect only this app's upstream feed. The app is unauthenticated and intended to remain bound to localhost; no deployment/access-control feature was added.

## Checks and limitations

Run `python3 -m unittest backend.test_live backend.test_timeframes backend.test_candles backend.test_recorder backend.test_history -v`, `node --test frontend/src/chartAdapter.test.js`, and `npm --prefix frontend run build`.

Constructed tests verify same-interval replacement, next-interval insertion, fresh reconnect snapshot, six fields, unknown volume, failed writes, status separation, manual disconnect and five-attempt bound. These tests use disposable SQLite and mocked callback inputs; they are not live evidence. Browser and actual Yahoo observations are recorded separately in verification.md. Live Yahoo volume remains unknown because its semantics are not established; the UI does not invent volume. Replay control UI and production-scale fanout remain outside this change.
