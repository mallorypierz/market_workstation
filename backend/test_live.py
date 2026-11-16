"""Constructed callbacks only, stored in disposable databases; not live evidence."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from fastapi import WebSocketDisconnect
from backend.live import LiveFeed
from backend.recorder import connect, snapshot
from backend.main import candle_stream


def message(time, price):
    return {"id": "AAPL", "time": str(int(datetime.fromisoformat(time.replace("Z", "+00:00")).timestamp()*1000)), "price": price}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "constructed.sqlite3"
        self.db = connect(self.path)
        self.feed = LiveFeed()

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_storage_failure_cannot_publish_success(self):
        with patch("backend.live.record", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                self.feed.accept(self.db, message("2026-11-09T14:30:05Z", 100))
        self.assertIsNone(self.feed.latest)
        self.assertEqual(snapshot(self.db)["observations"], [])

    def test_freshness_is_independent_of_socket(self):
        self.feed.connected = True
        self.assertEqual(self.feed.status()["status"], "connected")
        self.feed.latest = {"source_time": (datetime.now(timezone.utc)-timedelta(seconds=120)).isoformat()}
        self.assertEqual(self.feed.status()["status"], "stale")
        self.feed.connected = False
        self.feed.state = "unavailable"
        self.assertEqual(self.feed.status()["status"], "unavailable")

    def test_websocket_same_interval_next_interval_and_reconnect(self):
        feed, db = self.feed, self.db
        feed.accept(db, message("2026-11-09T14:30:05Z", 100))

        class Socket:
            def __init__(self, mutate):
                self.frames = []
                self.mutate = mutate
            async def accept(self): pass
            async def send_json(self, frame):
                if len(self.frames) == (3 if self.mutate else 1):
                    raise WebSocketDisconnect()
                self.frames.append(frame)
                if self.mutate and len(self.frames) == 1:
                    feed.accept(db, message("2026-11-09T14:30:20Z", 103))
                if self.mutate and len(self.frames) == 2:
                    feed.accept(db, message("2026-11-09T14:31:00Z", 101))

        first, reconnect = Socket(True), Socket(False)
        with patch.dict(os.environ, {"MARKET_DB_PATH": str(self.path)}), patch("backend.main.feed", feed), patch("backend.main.asyncio.sleep", new=AsyncMock()):
            asyncio.run(candle_stream(first, "AAPL", "1m", "yahoo"))
            asyncio.run(candle_stream(reconnect, "AAPL", "1m", "yahoo"))
        self.assertEqual([len(f["candles"]) for f in first.frames], [1, 1, 2])
        self.assertEqual(first.frames[1]["candles"][0]["close"], 103)
        self.assertEqual(first.frames[2]["candles"][1]["close"], 101)
        self.assertEqual(reconnect.frames[0]["candles"], first.frames[-1]["candles"])
        self.assertEqual(reconnect.frames[0]["type"], "snapshot")
        self.assertTrue(all(len(c)==6 for frame in first.frames for c in frame["candles"]))
        self.assertTrue(all(c["volume"] is None for c in first.frames[-1]["candles"]))

    def test_disconnect_control_does_not_delete_records(self):
        self.feed.accept(self.db, message("2026-11-09T14:30:05Z", 100))
        self.feed.connected = True
        asyncio.run(self.feed.stop())
        self.assertEqual(self.feed.status()["status"], "disconnected")
        self.assertEqual(len(snapshot(self.db)["observations"]), 1)

    def test_connection_failures_have_five_attempt_limit(self):
        socket = AsyncMock()
        socket.__aenter__.side_effect = ConnectionError("constructed failure")
        with patch.dict(os.environ, {"MARKET_DB_PATH": str(self.path)}), patch("backend.live.yf.AsyncWebSocket", return_value=socket), patch("backend.live.asyncio.sleep", new=AsyncMock()):
            asyncio.run(self.feed.run())
        self.assertEqual(socket.__aenter__.await_count, 5)
        self.assertFalse(self.feed.connected)
        self.assertEqual(self.feed.state, "unavailable")
