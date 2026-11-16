# One-minute aggregation rules

Implemented in `backend/candles.py` using saved observations, one source namespace and one ticker per request. No new dependency or schema change. Source payloads/deliveries/revision evidence are never overwritten. The existing HTTP CSV endpoint and Vue sample chart remain unchanged.

## Output and time

`aggregate(db, ticker, as_of=..., source=..., receipt_cutoff=..., cumulative_volume_field=...)` returns an envelope. Each element of `candles` has **exactly** timestamp, open, high, low, close, volume. Unknown volume is Python None / JSON null, never zero. `status[timestamp]` separately carries ended, volume_status, volume_reasons, and supporting observation_ids. The envelope also records receipt_cutoff and skipped_observation_ids.

UTC minute intervals are half-open: [minute start, next minute start). Source Unix milliseconds are floored to a 60,000 ms boundary; timestamp is that start in ISO UTC ending Z. An observation exactly at 15:01:00 belongs to 15:01, not 15:00. Timezone-aware as_of is required and normalized to UTC. Source times after as_of are excluded. No empty intervals or carried-forward synthetic prices are fabricated.

Ended means as_of >= minute start + 60 seconds. It does not mean the provider delivered all observations or that the candle can no longer change. Completion is computed, not persisted as an immutable final flag.

## Knowledge, price order and corrections

Use observations first delivered by receipt_cutoff, excluding only those explicitly superseded by a revision link known at that cutoff. The default cutoff is the largest committed receipt ID when aggregation begins; this provides a stable boundary for append-only data. as_of controls source eligibility and minute-end status; it does NOT automatically reconstruct receipt-time knowledge. Pass the relevant receipt_cutoff for historical replay. No assumption is made that wall-clock receipt timestamps equal receipt sequence order.

Sort by source_time_ms then observation_id. The first/last prices give open/close, and all active prices determine high/low. Equal-time messages have no provider sequence: observation_id is only a reproducible local tie-breaker. Ambiguous same-time changed messages both contribute to the price range; they are not silently treated as corrections. Exact repeat deliveries reuse their observation ID and enter aggregation only once.

Recompute from the selected immutable records whenever data changes. A late middle observation can alter high/low; a late earlier/later price can change open/close. This applies even after ended=true. An evidenced correction removes the earlier observation from the derived current view, while retaining both original payloads in SQLite. Old receipt cutoffs reproduce earlier knowledge. A correction to source time can move an observation between minutes; a volume correction or late baseline can affect subsequent intervals, so this implementation recomputes all selected minutes rather than only the changed minute. Competing explicit revision branches are not resolved into an invented provider order: their remaining observations both participate.

Malformed prices/missing source times are excluded with IDs reported in skipped_observation_ids. Original database evidence is retained. A caller must not hide this diagnostic when presenting a result as complete.

## Cumulative volume

Yahoo/AAPL now defaults to day_volume counter differencing, labeled observed_delta_estimate. Other sources still require explicit cumulative_volume_field. This is an interpretation of the daily equity counter, not a claim of exact exchange minute volume. Accept nonnegative integer totals, including integer strings; missing, invalid or fractional totals are unknown.

For each source-ordered observation, subtract the immediately previous valid cumulative total from its total. Assign that increment to the later observation's minute. Sum increments only when every increment within that minute can be determined. Never sum cumulative totals themselves. This is an observed-delta estimate: sparse snapshots can straddle a minute boundary and omit trades after the final sample. Even ended candles are not certified full exchange-minute volume.

The assignment uses a pre-minute baseline of 1000, then 1004, 1009, 1011: increments 4 + 5 + 2 = **11**. With the middle sample arriving late, increments first appear as 4 + 7 = 11; adding the missing middle sample splits 7 into 5 + 2 without double-counting.

A minute's volume is null if any increment has a missing/invalid baseline or total, decreasing total (reset), ambiguous same-source-time samples, unknown/changed session, or a baseline older than the immediately preceding minute. Missing baseline is not assumed to be zero. A reset makes that affected minute unknown; a later minute may recover once a valid post-reset baseline exists. Neither unknown volume nor repeated deliveries are interpreted as zero trades.

An explicit session_field can provide a documented session identifier. Without it, UTC date is a conservative partition to avoid carrying totals across days; it is **not** a verified exchange trading-session calendar. An intraday reset is detected by a decrease; unseen resets followed by a rebound cannot be inferred from sparse data. These limitations remain for live integration.

## Verification

Run `python3 -m unittest backend.test_candles backend.test_recorder backend.test_history -v`. All candle inputs in tests are constructed, not live Yahoo messages. See [verification results](verification.md) and [actual output](evidence/candle-aggregation.json).

History endpoint integration now passes `knowledge_at=as_of` to additionally filter receipt and revision-identification timestamps, and uses a SQLite read transaction for a consistent view. Standalone callers can still use receipt_cutoff without this optional wall-clock filter. See [timeframes](timeframes.md) for session grouping and HTTP behavior.
