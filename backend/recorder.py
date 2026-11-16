"""Append-only decoded observations and every delivery, using standard-library SQLite."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]


def database_path():
    path = Path(os.environ.get("MARKET_DB_PATH", "backend/data/market.sqlite3")).expanduser()
    return path if path.is_absolute() else ROOT / path


def connect(path=None):
    path = Path(path) if path is not None else database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
            observation_id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            ticker TEXT NOT NULL,
            source_time_json TEXT NOT NULL,
            source_time_ms INTEGER,
            payload_json TEXT NOT NULL,
            UNIQUE(source, payload_json)
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_id INTEGER NOT NULL REFERENCES observations(observation_id),
            receipt_time TEXT NOT NULL,
            decoded_message_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS revisions (
            revision_id INTEGER PRIMARY KEY,
            earlier_id INTEGER NOT NULL REFERENCES observations(observation_id),
            later_id INTEGER NOT NULL REFERENCES observations(observation_id),
            identified_at_receipt_id INTEGER NOT NULL REFERENCES deliveries(receipt_id),
            evidence TEXT NOT NULL,
            CHECK (earlier_id <> later_id),
            UNIQUE(earlier_id, later_id)
        );
        CREATE INDEX IF NOT EXISTS observations_source_time
            ON observations(source, ticker, source_time_ms, observation_id);
        CREATE INDEX IF NOT EXISTS deliveries_observation ON deliveries(observation_id, receipt_id);
    """)
    return db


def record(db, payload, receipt_time, *, source="yahoo", revision_of=None, revision_evidence=None):
    """Only explicit, evidenced corrections get revision links; time alone is not identity."""
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str) or not payload["id"]:
        raise ValueError("A decoded message with a nonempty ticker id is required")
    stamp = datetime.fromisoformat(receipt_time.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Receipt timestamp must include its timezone")
    receipt_time = stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    original = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    raw_time = payload.get("time")
    try:
        source_ms = int(raw_time) if isinstance(raw_time, (str, int)) and not isinstance(raw_time, bool) else None
        if source_ms is not None and not -(2**63) <= source_ms < 2**63:
            source_ms = None
    except ValueError:
        source_ms = None
    # Serialize concurrent writers before looking up identity; commit before returning.
    db.execute("BEGIN IMMEDIATE")
    try:
        previous = db.execute("SELECT observation_id FROM observations WHERE source=? AND payload_json=?",
                              (source, canonical)).fetchone()
        duplicate = previous is not None
        if previous:
            observation_id = previous[0]
        else:
            observation_id = db.execute(
                "INSERT INTO observations(source,ticker,source_time_json,source_time_ms,payload_json) VALUES(?,?,?,?,?)",
                (source, payload["id"], json.dumps(raw_time), source_ms, canonical)).lastrowid
        receipt_id = db.execute(
            "INSERT INTO deliveries(observation_id,receipt_time,decoded_message_json) VALUES(?,?,?)",
            (observation_id, receipt_time, original)).lastrowid
        if revision_of is not None:
            earlier = db.execute("SELECT source,ticker FROM observations WHERE observation_id=?", (revision_of,)).fetchone()
            if not earlier or tuple(earlier) != (source, payload["id"]) or revision_of >= observation_id or not revision_evidence:
                raise ValueError("Revision requires an earlier same-source/ticker observation and explicit evidence")
            db.execute("INSERT OR IGNORE INTO revisions(earlier_id,later_id,identified_at_receipt_id,evidence) VALUES(?,?,?,?)",
                       (revision_of, observation_id, receipt_id, revision_evidence))
        db.commit()
        return {"observation_id": observation_id, "receipt_id": receipt_id, "exact_repeat": duplicate}
    except Exception:
        db.rollback()
        raise


def snapshot(db):
    return {table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {key}")]
            for table, key in [("observations", "observation_id"), ("deliveries", "receipt_id"), ("revisions", "revision_id")]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "snapshot", "record-test"])
    args = parser.parse_args()
    db = connect()
    try:
        if args.command == "init":
            print(json.dumps({"database": str(database_path()), "initialized": True}))
        elif args.command == "snapshot":
            print(json.dumps(snapshot(db), indent=2))
        else:
            for line in sys.stdin:
                item = json.loads(line)
                print(json.dumps(record(db, item["payload"], item["receipt_time"], source="constructed-test")))
    finally:
        db.close()


if __name__ == "__main__":
    main()
