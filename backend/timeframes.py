"""Derive regular-session candles from a single selected one-minute view."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import sqlite3

import exchange_calendars as calendars

from backend.candles import aggregate, utc
from backend.history import read_candles
from backend.recorder import database_path

TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": None}
SYMBOL_CALENDARS = {"SAMPLE": "XNAS", "AAPL": "XNAS"}


def iso(stamp):
    return stamp.isoformat().replace("+00:00", "Z")


@lru_cache(maxsize=16)
def calendar_for(code, year):
    return calendars.get_calendar(code, start=f"{year}-01-01", end=f"{year}-12-31")


def resample(minutes, *, timeframe, symbol, as_of, minute_status=None):
    """Input must contain one current value per minute, selected before resampling."""
    if timeframe not in TIMEFRAMES or symbol not in SYMBOL_CALENDARS:
        raise ValueError("Unsupported timeframe or symbol")
    now = utc(as_of)
    groups, seen, excluded = {}, set(), []
    for candle in sorted(minutes, key=lambda row: row["timestamp"]):
        stamp = utc(candle["timestamp"])
        if stamp.second or stamp.microsecond:
            raise ValueError("Expected minute-start timestamps")
        if stamp in seen:
            raise ValueError("Select revisions before resampling: duplicate minute")
        seen.add(stamp)
        if stamp > now:
            continue
        calendar = calendar_for(SYMBOL_CALENDARS[symbol], stamp.year)
        day = stamp.date().isoformat()
        if day not in calendar.schedule.index:
            excluded.append(candle["timestamp"])
            continue
        session = calendar.schedule.loc[day]
        opening, closing = session["open"].to_pydatetime(), session["close"].to_pydatetime()
        if not opening <= stamp < closing:
            excluded.append(candle["timestamp"])
            continue
        width = TIMEFRAMES[timeframe]
        offset = int((stamp - opening).total_seconds() // 60)
        start = opening if width is None else opening + timedelta(minutes=offset // width * width)
        end = closing if width is None else min(start + timedelta(minutes=width), closing)
        group = groups.setdefault(start, {"end": end, "session_open": opening, "rows": [], "ended_minutes": True})
        group["rows"].append(candle)
        ended = now >= stamp + timedelta(minutes=1)
        if minute_status is not None:
            ended = ended and minute_status.get(candle["timestamp"], {}).get("ended", False)
        group["ended_minutes"] &= ended
    candles, status = [], {}
    for start, group in sorted(groups.items()):
        rows = group["rows"]
        volumes_known = all(row["volume"] is not None for row in rows)
        expected = int((group["end"] - start).total_seconds() // 60)
        coverage = len(rows) == expected
        ended = now >= group["end"]
        timestamp = iso(start)
        candles.append({"timestamp": timestamp, "open": rows[0]["open"],
                        "high": max(row["high"] for row in rows), "low": min(row["low"] for row in rows),
                        "close": rows[-1]["close"], "volume": sum(row["volume"] for row in rows) if volumes_known else None})
        quality = {minute_status.get(row["timestamp"], {}).get("volume_status", "unknown") for row in rows} if minute_status is not None else {"provided_minute_volume"}
        status[timestamp] = {"session_open": iso(group["session_open"]), "interval_end": iso(group["end"]),
                             "present_minutes": len(rows), "expected_minutes": expected,
                             "coverage_complete": coverage, "ended": ended,
                             "complete": ended and coverage and group["ended_minutes"],
                             "volume_known_for_present_minutes": volumes_known,
                             "volume_status": "unknown" if not volumes_known else ("partial_coverage_sum" if not coverage else "sum_of_minutes"),
                             "underlying_volume_quality": sorted(quality)}
    return {"candles": candles, "status": status, "excluded_outside_session": excluded}


def history_view(*, symbol="SAMPLE", timeframe="1m", source="sample", as_of=None, receipt_cutoff=None):
    now = utc(as_of or datetime.now(timezone.utc))
    symbol = symbol.upper()
    if symbol not in SYMBOL_CALENDARS:
        raise ValueError("Supported symbols: SAMPLE (synthetic CSV) and AAPL (Yahoo SQLite)")
    if (source == "sample" and symbol != "SAMPLE") or (source == "yahoo" and symbol != "AAPL"):
        raise ValueError("Use symbol=SAMPLE for sample data or symbol=AAPL for Yahoo records")
    if source == "sample":
        if receipt_cutoff is not None:
            raise ValueError("receipt_cutoff only applies to recorded Yahoo observations")
        # Full CSV minutes cannot reveal their final OHLC before minute end.
        minutes = [row for row in read_candles() if utc(row["timestamp"]) + timedelta(minutes=1) <= now]
        minute_status = None
        diagnostics = {}
    elif source == "yahoo":
        path = database_path()
        if not path.exists():
            minutes, minute_status = [], {}
            diagnostics = {"database_initialized": False}
        else:
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            db.row_factory = sqlite3.Row
            try:
                db.execute("BEGIN")
                view = aggregate(db, symbol, as_of=now, knowledge_at=now, receipt_cutoff=receipt_cutoff)
            finally:
                db.close()
            minutes, minute_status = view["candles"], view["status"]
            diagnostics = {"database_initialized": True, "receipt_cutoff": view["receipt_cutoff"],
                           "skipped_observation_ids": view["skipped_observation_ids"]}
    else:
        raise ValueError("Unsupported source")
    result = resample(minutes, timeframe=timeframe, symbol=symbol, as_of=now, minute_status=minute_status)
    return {"symbol": symbol, "source": "synthetic-csv" if source == "sample" else "yahoo-recorded",
            "timeframe": timeframe, "as_of": iso(now), "calendar": "XNAS (library alias XNYS)",
            **result, **diagnostics}
