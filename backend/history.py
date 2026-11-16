"""Synthetic one-minute practice candles; not a live market source."""
import csv
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED = ROOT / "prompts/data/sample-candles.csv"
DEFAULT_CSV = SUPPLIED if SUPPLIED.is_file() else ROOT / "backend/data/sample-candles.csv"
FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def read_candles(path: Path = DEFAULT_CSV) -> list[dict]:
    """Read UTC minute starts, numeric OHLC, and per-minute share volume."""
    candles = []
    seen = set()
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != FIELDS:
            raise ValueError("Expected exactly timestamp,open,high,low,close,volume")
        for row in reader:
            if set(row) != set(FIELDS) or any(v is None for v in row.values()):
                raise ValueError("Each row must contain exactly six values")
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("Timestamps must be UTC")
            if stamp.second or stamp.microsecond:
                raise ValueError("Timestamps must mark minute starts")
            timestamp = stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if timestamp in seen:
                raise ValueError("Duplicate minute for this single-instrument fixture")
            seen.add(timestamp)
            prices = {key: float(row[key]) for key in FIELDS[1:5]}
            volume = int(row["volume"])
            if not all(isfinite(value) for value in prices.values()) or volume < 0:
                raise ValueError("Prices must be finite and volume nonnegative")
            if not (prices["low"] <= min(prices["open"], prices["close"])
                    <= max(prices["open"], prices["close"]) <= prices["high"]):
                raise ValueError("Invalid OHLC range")
            candles.append({"timestamp": timestamp, **prices, "volume": volume})
    return sorted(candles, key=lambda candle: candle["timestamp"])
