"""One managed Yahoo subscription; storage precedes all client-visible updates."""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import os

import yfinance as yf
from websockets.protocol import State

from backend.feed_probe import utc_now
from backend.recorder import connect, record
from backend.paper import process_live
from backend.timeframes import calendar_for, history_view


class LiveFeed:
    def __init__(self):
        self.task = None
        self.connected = False
        self.enabled = False
        self.state = "disconnected"
        self.error = None
        self.latest = None
        self.attempt = 0

    def accept(self, db, message):
        receipt = utc_now()
        if message.get("id") != "AAPL" or "price" not in message:
            return
        stored = record(db, message, receipt, source="yahoo")
        process_live(db)
        try:
            source = datetime.fromtimestamp(int(message["time"]) / 1000, timezone.utc)
            source_time = source.isoformat().replace("+00:00", "Z")
        except (KeyError, ValueError, TypeError, OSError, OverflowError):
            source_time = None
        self.latest = {**stored, "source_time": source_time, "receipt_time": receipt,
                       "price": message["price"], "source_time_raw": message.get("time")}

    async def start(self):
        if self.task and not self.task.done():
            return
        self.enabled = True
        self.error = None
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.enabled = False
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.connected = False
        self.state = "disconnected"

    async def run(self):
        db = connect()
        try:
            for attempt in range(1, 6):
                self.attempt = attempt
                self.state = "connecting"
                ws = yf.AsyncWebSocket(verbose=False)
                listener = None
                try:
                    async with asyncio.timeout(12):
                        await ws.__aenter__()
                        await ws.subscribe(["AAPL"])
                    self.connected = True
                    self.state = "connected"
                    self.error = None
                    # Callback exceptions are recorded explicitly: yfinance otherwise logs and swallows them.
                    failure = []
                    def receive(message):
                        try:
                            self.accept(db, message)
                        except Exception as error:
                            failure.append(type(error).__name__)
                    listener = asyncio.create_task(ws.listen(receive))
                    while not listener.done():
                        await asyncio.sleep(0.5)
                        if failure:
                            raise RuntimeError("storage_or_message_error")
                        # Pinned yfinance 1.8.0 exposes its transport here. Do not equate task activity with connectivity.
                        if ws._ws is None or ws._ws.state is not State.OPEN:
                            raise ConnectionError("upstream_closed")
                    await listener
                    raise ConnectionError("upstream_listener_ended")
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    self.error = type(error).__name__
                    self.state = "unavailable"
                finally:
                    self.connected = False
                    if listener:
                        listener.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await asyncio.wait_for(listener, 3)
                    with suppress(Exception):
                        await asyncio.wait_for(ws.close(), 3)
                if attempt < 5:
                    await asyncio.sleep(min(2 ** attempt, 16))
            self.state = "unavailable"
        finally:
            self.connected = False
            db.close()

    def status(self):
        now = datetime.now(timezone.utc)
        age = None
        if self.latest and self.latest["source_time"]:
            age = (now - datetime.fromisoformat(self.latest["source_time"].replace("Z", "+00:00"))).total_seconds()
        state = self.state
        if self.connected:
            state = "connected" if age is None else ("receiving" if 0 <= age <= 30 else "stale")
        calendar = calendar_for("XNAS", now.year)
        day = now.date().isoformat()
        session = "closed"
        if day in calendar.schedule.index:
            schedule = calendar.schedule.loc[day]
            if schedule["open"] <= now < schedule["close"]:
                session = "regular session"
        return {"status": state, "upstream_connected": self.connected, "enabled": self.enabled,
                "source_age_seconds": age, "latest": self.latest, "market_session": session,
                "attempt": self.attempt, "error_type": self.error}


def stream_view(feed, symbol, timeframe, source):
    view = history_view(symbol=symbol, timeframe=timeframe, source=source)
    view["feed"] = feed.status() if source == "yahoo" else {
        "status": "synthetic", "upstream_connected": False, "enabled": False,
        "source_age_seconds": None, "latest": None, "market_session": "synthetic sample"}
    return view
