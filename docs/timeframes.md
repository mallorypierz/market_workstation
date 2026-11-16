# Session-based history timeframes

Implemented in `backend/timeframes.py`, using exchange-calendars 4.13.2 and the existing one-minute sources. Larger candles are derived on every request; there is no independent higher-timeframe source or cache of candle values.

## HTTP contract

`GET /api/history` still returns the existing synthetic three-minute array by default. Supported query parameters:

| Parameter | Values / behavior |
| --- | --- |
| timeframe | 1m (default), 5m, 15m, 1h, 1d |
| source | sample (default), yahoo (recorded SQLite observations, not an on-demand live subscription) |
| symbol | SAMPLE (default, anonymous synthetic CSV), AAPL (Yahoo SQLite). Source and symbol must match. Other symbols require an explicit exchange mapping before support. |
| as_of | Timezone-aware ISO displayed time; defaults to UTC now. Encode a plus sign in a numeric offset as %2B, or use Z. |
| receipt_cutoff | Optional nonnegative SQLite delivery-ID ceiling, applied in addition to displayed time; rejected for sample source. |
| include_metadata | false (default): six-field candle array. true: envelope with candles plus separate status, source, symbol, timeframe and as_of. |

Each candle contains exactly `timestamp, open, high, low, close, volume`. Unknown volume is JSON null. Response headers X-Data-Source, X-Timeframe and X-Symbol identify the request result. Metadata-aware clients should request include_metadata=true to avoid presenting partial groups as complete. Existing Vue continues to request the compatible one-minute array; no timeframe selector was added in this task.

Examples:

```text
/api/history?symbol=SAMPLE&timeframe=5m&include_metadata=true
/api/history?symbol=SAMPLE&timeframe=1d&include_metadata=true
/api/history?symbol=SAMPLE&timeframe=5m&as_of=2026-11-09T14:31:00Z&include_metadata=true
/api/history?source=yahoo&symbol=AAPL&timeframe=15m&include_metadata=true
```

Unsupported timeframes/symbols, mismatched source/symbol, invalid/naive times, or negative receipt cutoffs return 422. Missing Yahoo database returns empty candles with database_initialized=false in metadata; no fixture is substituted and a read request does not create the database.

## Regular sessions and alignment

Use XNAS for the supported Nasdaq path; this library maps XNAS to XNYS's regular US equity schedule. The anonymous synthetic CSV is explicitly assigned this calendar for practice; it is not relabeled as actual AAPL data. Schedules include holidays, early closes and America/New_York DST transitions. Package schedules are local rules, not a real-time exchange-notice service; exceptional newly announced closures require calendar updates/verification. Calendar objects are cached by year, not candle results.

Membership is `[session open, session close)` and minute timestamps must be exact minute starts. Ignore outside-session minutes with their timestamps reported in excluded_outside_session. Intraday group start is `session_open + floor(minutes_since_open / width) * width`. The final group is truncated at session close. Hourly means 09:30–10:30 local, not calendar-clock 09:00–10:00. Daily covers one session and is timestamped at that session's open in UTC. Gaps do not create a new session or shift group boundaries. No empty groups or invented zero-volume minutes are emitted. Only the configured US equity schedule is supported; this implementation is not generalized to overnight exchanges or lunch-break calendars.

## Reduction and metadata

Select the current one-minute view first, then sort by timestamp and take first open, max high, min low, last close, and sum of the present minute volumes. If any present minute has unknown volume, group volume is null. Known-zero minute volume remains numeric 0. A numeric partial-coverage sum (e.g. 3550) is not the full interval's total.

Status is keyed by candle timestamp and records session_open, interval_end, present_minutes, expected_minutes, coverage_complete, ended, complete, volume_known_for_present_minutes, volume_status and underlying_volume_quality. Expected minutes count the whole scheduled interval, including early-close truncation. `coverage_complete` means every minute slot is present. `ended` only means displayed time reached the interval end. `complete` requires ended, full slot coverage and ended constituent minutes; it does not certify market-provider completeness or volume accuracy. A full-coverage candle can still have unknown volume; those facts are deliberately separate. Existing observed-delta volume quality propagates through underlying_volume_quality.

## Replay, availability and corrections

Sample CSV rows are final minute OHLC, so a row is unavailable until its minute END is at or before as_of. This prevents revealing final close/high/low before they could have been known. The static fixture has no historical receipt/revision log; this is a documented synthetic availability convention.

For Yahoo, open SQLite read-only in a read transaction and derive one-minute candles from observations whose source time AND at least one receipt time are at/before displayed time, also respecting receipt_cutoff. Apply a correction only if its identifying delivery satisfies both limits. Receipt timestamps are compared as instants with SQLite julianday, independently of receipt-ID order, preventing later-recorded corrections from leaking into replay. Raw observations and revision history remain unchanged.

Recompute affected minute values from the selected observation view, and resample that unique minute list. A correction therefore replaces that minute's earlier derived value instead of adding both. Resampling rejects duplicate minute timestamps rather than guessing revision ordering. Higher buckets and daily results are rebuilt on request, including effects of late arrivals and changes spanning minute boundaries. No persistently cached higher candles can become stale.

Default Yahoo minute volume remains unknown because live cumulative semantics are not verified. Constructed tests validate arithmetic without claiming live feed behavior. No network subscription is started by the history route.

## References and evidence

[Official exchange-calendars documentation](https://github.com/gerrymanoim/exchange_calendars) and [calendar alias definitions](https://github.com/gerrymanoim/exchange_calendars/blob/master/exchange_calendars/calendar_utils.py).

[Verification log](verification.md), [constructed comparisons](evidence/timeframe-comparisons.json), [actual HTTP responses](evidence/timeframe-http.json).
