# Recorded-session replay

Replay uses the existing SQLite observation/delivery/revision store and Python minute/timeframe calculations. Vue does not calculate OHLC or volume. Start FastAPI with `MARKET_FEED_ENABLED=0` and select **Replay**. Entering Replay also disconnects the shared upstream subscription. Only saved, supported symbols appear (currently AAPL); unsupported exchange mappings are not invented.

Select a UTC **receipt-time** range: start inclusive, end exclusive. Load selection, then Play replay, Pause replay, Next observation, or Restart replay. Timeframes use the same regular-session backend calculation as live history. Empty selections explicitly say they have no recorded observations. Recorded premarket deliveries advance the replay even when they produce no regular-session candle.

```text
SQLite observations + original deliveries + explicit revision evidence
    | read-only connection, fixed maximum receipt ID, receipt-time selection
    v
Original receipt-ID order, one additional delivery per replay step
    | original source times preserved; no future receipts visible
    v
Existing Python minute candles -> existing requested-timeframe aggregation
    | GET /api/replay: six candle fields + separate replay/completion metadata
    v
Vue Replay chart, original source/receipt time, observation and receipt IDs
```

`GET /api/recordings` lists saved Yahoo symbols and receipt bounds. `GET /api/replay` takes symbol, start, end, timeframe (default 1m), step (default 0), and optional snapshot_cutoff. The first response fixes the maximum receipt ID; subsequent steps and restarts retain it. Each request opens SQLite with `mode=ro`, `query_only=ON`, and a read transaction. Replay never inserts observations/deliveries or writes playback progress. The endpoint rejects replay while the managed Yahoo feed is enabled or connected.

Arrival order is durable `receipt_id` order, including exact duplicate deliveries. Price ordering within each candle still uses original source time and the existing deterministic tie rule. A late message changes the earlier source-time candle only at its replay receipt step. Explicit correction links suppress the earlier value only once the identifying receipt is visible; both recorded values remain stored. Changed messages without correction evidence remain distinct. Exact repeated deliveries do not create a second price observation or double-count volume.

Only deliveries inside the selected receipt range participate; there is no automatic pre-range candle or volume baseline. Source timestamps can fall outside that range. The display clock is the greatest receipt time seen so far (or selection start), so clock regression cannot move completion backwards. Completion uses that replay clock, never today's wall clock. Ending playback freezes the last receipt time: a final candle can correctly remain **Still forming**. Replay completion and candle completion are different.

Playback is accelerated, sequential HTTP stepping (80 ms minimum delay plus calculation/request time), not a simulation of original wall-clock delays. Each step recomputes an authoritative view using only selected receipts so older candles can change. This favors correctness for short local captures; large sessions need indexing/caching/paging work. The fixed receipt ceiling assumes the recorder's append-only contract; manually editing stored rows is unsupported.

Yahoo minute volume remains `null`/Unknown: raw day_volume and last_size are preserved, but current evidence does not establish a reliable complete minute-volume calculation. Replay does not sum cumulative totals or pretend Unknown is zero. Known cumulative-volume behavior is tested separately with constructed input in disposable databases.

Verification uses the actual saved AAPL capture from 2026-11-12, not synthetic data. See [verification](verification.md), [comparison evidence](evidence/replay-check.json), and [repeat screenshot](evidence/replay-repeat.png). Numeric actual-capture minute-volume verification remains open.
