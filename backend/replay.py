"""Read-only replay of a fixed selection, in durable original receipt order."""
from contextlib import contextmanager
from datetime import timedelta
import json
import sqlite3

from backend.candles import aggregate, utc
from backend.recorder import database_path
from backend.timeframes import resample, iso, SYMBOL_CALENDARS, TIMEFRAMES


@contextmanager
def recorded_database():
    path = database_path()
    if not path.exists():
        yield None
        return
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        yield db
    finally:
        db.close()


def recordings():
    with recorded_database() as db:
        if db is None:
            return []
        rows = db.execute("""SELECT o.ticker AS symbol, COUNT(*) AS deliveries,
            MIN(d.receipt_time) AS start, MAX(d.receipt_time) AS last_receipt
            FROM deliveries d JOIN observations o USING(observation_id)
            WHERE o.source='yahoo' GROUP BY o.ticker ORDER BY o.ticker""").fetchall()
        return [{**dict(row), "end": iso(utc(row["last_receipt"]) + timedelta(microseconds=1))}
                for row in rows if row["symbol"] in SYMBOL_CALENDARS]


def replay_view(*, symbol, start, end, timeframe="1m", step=0, snapshot_cutoff=None, source="yahoo"):
    beginning, ending = utc(start), utc(end)
    if beginning >= ending or step < 0:
        raise ValueError("Use a nonempty UTC receipt-time range and nonnegative step")
    if symbol not in SYMBOL_CALENDARS or timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported saved symbol or timeframe")
    with recorded_database() as db:
        ceiling = 0 if db is None else db.execute("SELECT COALESCE(MAX(receipt_id),0) FROM deliveries").fetchone()[0]
        ceiling = min(ceiling, snapshot_cutoff) if snapshot_cutoff is not None else ceiling
        candidates = [] if db is None else db.execute("""
            SELECT d.*, o.source_time_ms, o.ticker FROM deliveries d
            JOIN observations o USING(observation_id)
            WHERE o.source=? AND o.ticker=? AND d.receipt_id<=? ORDER BY d.receipt_id
        """, (source, symbol, ceiling)).fetchall()
        # Python aware datetime comparison preserves microseconds and handles nonmonotonic receipt clocks.
        selected = [row for row in candidates if beginning <= utc(row["receipt_time"]) < ending]
        position = min(step, len(selected))
        visible = selected[:position]
        current = visible[-1] if visible else None
        # Receipt ID controls order; the replay display clock never runs backwards.
        clock = max([beginning] + [utc(row["receipt_time"]) for row in visible])
        if visible:
            minutes = aggregate(db, symbol, source=source, as_of=clock,
                                receipt_cutoff=current["receipt_id"], replay_receipt_ids=[row["receipt_id"] for row in visible])
            view = resample(minutes["candles"], symbol=symbol, timeframe=timeframe,
                            as_of=clock, minute_status=minutes["status"])
        else:
            view = {"candles": [], "status": {}, "excluded_outside_session": []}
        latest = None
        if current:
            payload = json.loads(current["decoded_message_json"])
            try:
                from datetime import datetime, timezone
                source_time = iso(datetime.fromtimestamp(int(payload["time"])/1000, timezone.utc))
            except (KeyError, TypeError, ValueError, OSError, OverflowError):
                source_time = None
            latest = {"observation_id": current["observation_id"], "receipt_id": current["receipt_id"],
                      "source_time": source_time, "receipt_time": current["receipt_time"], "price": payload.get("price")}
        return {"type": "replay", "symbol": symbol, "timeframe": timeframe, "source": f"replay:{source}",
                "as_of": iso(clock), **view,
                "replay": {"step": position, "total": len(selected), "finished": position == len(selected),
                           "empty": not selected, "snapshot_cutoff": ceiling, "start": iso(beginning), "end": iso(ending)},
                "feed": {"status": "replay", "upstream_connected": False, "enabled": False,
                         "source_age_seconds": None, "latest": latest, "market_session": "recorded session"}}
