"""One-minute source-time candles derived from immutable recorded observations."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math

from backend.recorder import connect


def utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if stamp.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    return stamp.astimezone(timezone.utc)


def volume_total(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            return None
    return value if isinstance(value, int) and value >= 0 else None


def aggregate(db, ticker, *, as_of, source="yahoo", receipt_cutoff=None,
              cumulative_volume_field=None, session_field=None, knowledge_at=None, replay_receipt_ids=None):
    """Return six-field candles plus separate status; volume semantics require opt-in.

    as_of controls elapsed time and rejects future source timestamps. receipt_cutoff
    controls what recorded knowledge is used, independently of the wall clock.
    """
    now = utc(as_of)
    now_ms = int(now.timestamp() * 1000)
    knowledge_time = utc(knowledge_at).isoformat() if knowledge_at is not None else None
    selected_receipts = json.dumps(replay_receipt_ids) if replay_receipt_ids is not None else None
    if receipt_cutoff is None:
        receipt_cutoff = db.execute("SELECT COALESCE(MAX(receipt_id),0) FROM deliveries").fetchone()[0]
    rows = db.execute("""
        SELECT o.* FROM observations o
        WHERE o.source=? AND o.ticker=?
          AND EXISTS (SELECT 1 FROM deliveries d WHERE d.observation_id=o.observation_id AND d.receipt_id<=?
              AND (? IS NULL OR d.receipt_id IN (SELECT value FROM json_each(?)))
              AND (? IS NULL OR julianday(d.receipt_time)<=julianday(?)))
          AND NOT EXISTS (SELECT 1 FROM revisions r JOIN deliveries rd ON rd.receipt_id=r.identified_at_receipt_id
              WHERE r.earlier_id=o.observation_id AND r.identified_at_receipt_id<=?
              AND (? IS NULL OR r.identified_at_receipt_id IN (SELECT value FROM json_each(?)))
              AND (? IS NULL OR julianday(rd.receipt_time)<=julianday(?)))
        ORDER BY o.source_time_ms, o.observation_id
    """, (source, ticker, receipt_cutoff, selected_receipts, selected_receipts, knowledge_time, knowledge_time,
          receipt_cutoff, selected_receipts, selected_receipts, knowledge_time, knowledge_time)).fetchall()
    events, skipped = [], []
    for row in rows:
        payload = json.loads(row["payload_json"])
        price, time = payload.get("price"), row["source_time_ms"]
        if time is None or isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price):
            skipped.append(row["observation_id"])
            continue
        if time > now_ms:
            continue
        try:
            stamp = datetime.fromtimestamp(time / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            skipped.append(row["observation_id"])
            continue
        events.append({"id": row["observation_id"], "time": time, "price": price,
                       "minute": time // 60000 * 60000,
                       "total": volume_total(payload.get(cumulative_volume_field)) if cumulative_volume_field else None,
                       "session": payload.get(session_field) if session_field else stamp.date().isoformat()})
    counts = Counter(event["time"] for event in events)
    groups = {}
    previous = None
    for event in events:
        minute = event["minute"]
        group = groups.setdefault(minute, {"prices": [], "volume": 0, "reasons": set(), "ids": []})
        group["prices"].append(event["price"])
        group["ids"].append(event["id"])
        reason = None
        if not cumulative_volume_field:
            reason = "cumulative_volume_semantics_unverified"
        elif event["total"] is None:
            reason = "missing_or_invalid_total"
        elif previous is None or previous["total"] is None:
            reason = "missing_baseline"
        elif event["session"] is None or previous["session"] != event["session"]:
            reason = "session_boundary_or_unknown_session"
        elif counts[event["time"]] > 1 or counts[previous["time"]] > 1:
            reason = "ambiguous_same_time_messages"
        elif event["total"] < previous["total"]:
            reason = "cumulative_total_reset"
        elif previous["minute"] < minute - 60000:
            reason = "baseline_gap_spans_minutes"
        if reason:
            group["reasons"].add(reason)
        else:
            group["volume"] += event["total"] - previous["total"]
        previous = event
    candles, statuses = [], {}
    for minute, group in sorted(groups.items()):
        timestamp = datetime.fromtimestamp(minute / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
        prices = group["prices"]
        reasons = sorted(group["reasons"])
        candles.append({"timestamp": timestamp, "open": prices[0], "high": max(prices),
                        "low": min(prices), "close": prices[-1], "volume": None if reasons else group["volume"]})
        statuses[timestamp] = {"ended": now_ms >= minute + 60000,
                               "volume_status": "unknown" if reasons else "observed_delta_estimate",
                               "volume_reasons": reasons, "observation_ids": group["ids"]}
    return {"candles": candles, "status": statuses, "receipt_cutoff": receipt_cutoff,
            "skipped_observation_ids": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--source", default="yahoo")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--receipt-cutoff", type=int)
    parser.add_argument("--cumulative-volume-field", help="Only set when cumulative semantics are established")
    parser.add_argument("--session-field", help="Optional documented session identifier field")
    args = parser.parse_args()
    db = connect()
    try:
        print(json.dumps(aggregate(db, args.symbol, as_of=args.as_of or datetime.now(timezone.utc),
                                  source=args.source, receipt_cutoff=args.receipt_cutoff,
                                  cumulative_volume_field=args.cumulative_volume_field,
                                  session_field=args.session_field), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
