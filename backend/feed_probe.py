"""Bounded, unauthenticated Yahoo subscription; does not feed the sample chart."""
import argparse
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import logging
import subprocess
import sys
from backend.recorder import connect, database_path, record


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


async def probe(symbol, seconds):
    import yfinance as yf
    import websockets

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    opened = False
    received = asyncio.Event()
    listener = None
    ws = yf.AsyncWebSocket(verbose=False)
    db = connect()
    storage_failed = False
    emit("start", ticker=symbol, receipt_time=utc_now(), timeout_seconds=seconds,
         python=sys.executable, yfinance=yf.__version__, websockets=websockets.__version__)

    def on_message(message):
        nonlocal storage_failed
        receipt = utc_now()  # Capture before parsing or formatting source data.
        if received.is_set() or message.get("id") != symbol or "price" not in message:
            return
        try:
            stored = record(db, message, receipt, source="yahoo")
        except Exception as error:
            storage_failed = True
            emit("storage_error", error_type=type(error).__name__, receipt_time=receipt)
            received.set()  # Wake supervisor, but do not claim receipt was persisted.
            return
        raw_time = message.get("time")
        source_time = None
        # Candidate unit, not a provider guarantee: retain original for investigation.
        try:
            source_time = datetime.fromtimestamp(int(raw_time) / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, TypeError, OverflowError, OSError):
            pass
        volume = {key: value for key, value in message.items()
                  if "vol" in key.lower() or key == "last_size"}
        age = None
        if source_time:
            age = (datetime.fromisoformat(receipt.replace("Z", "+00:00")) -
                   datetime.fromisoformat(source_time.replace("Z", "+00:00"))).total_seconds()
        emit("observation", ticker=message["id"], price=message["price"],
             source_time_raw=raw_time, source_time_assuming_unix_ms=source_time,
             receipt_time=receipt, source_age_seconds_assuming_ms=age,
             volume_fields=volume, payload=message, stored=stored, database=str(database_path()))
        received.set()

    try:
        async with asyncio.timeout(seconds):
            await ws.__aenter__()
            opened = True
            emit("socket_open", receipt_time=utc_now())
            await ws.subscribe([symbol])
            emit("subscription_sent", ticker=symbol, receipt_time=utc_now())
            listener = asyncio.create_task(ws.listen(on_message))
            await received.wait()
    except TimeoutError:
        emit("timeout", receipt_time=utc_now())
    except Exception as error:
        # No arbitrary exception text/URLs: avoids leaking proxy credentials.
        emit("connection_error", error_type=type(error).__name__, receipt_time=utc_now())
    finally:
        if listener:
            listener.cancel()
            with suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(listener, timeout=3)
        with suppress(Exception):
            await asyncio.wait_for(ws.close(), timeout=3)
        db.close()
    emit("result", socket_opened=opened, observation_received=received.is_set(),
         persisted=received.is_set() and not storage_failed,
         receipt_verification="verified" if received.is_set() else "unverified",
         freshness="inspect source time; socket connectivity is not freshness")
    return 0 if received.is_set() and not storage_failed else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error("--seconds must be between 1 and 300")
    if args.worker:
        return asyncio.run(probe(args.symbol.upper(), args.seconds))
    # Hard process deadline also bounds imports, library retries and cleanup.
    try:
        result = subprocess.run([sys.executable, "-u", "-m", "backend.feed_probe",
                                 "--worker", "--symbol", args.symbol,
                                 "--seconds", str(args.seconds)], timeout=args.seconds + 15)
        return result.returncode
    except subprocess.TimeoutExpired:
        emit("hard_timeout", receipt_verification="unverified",
             note="Worker killed; consult preceding events for socket-open evidence")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
