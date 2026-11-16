import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import asyncio
from contextlib import redirect_stdout
import io

from backend.recorder import connect, record, snapshot, ROOT

PAYLOAD = {"id": "AAPL", "time": "1794234600000", "price": 100.0, "day_volume": "1200"}
RECEIPT = "2026-11-09T14:30:01Z"


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "constructed.sqlite3"
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_repeat_and_ambiguous_changed_value(self):
        first = record(self.db, PAYLOAD, RECEIPT, source="constructed-test")
        repeat = record(self.db, dict(reversed(list(PAYLOAD.items()))), RECEIPT, source="constructed-test")
        changed = record(self.db, {**PAYLOAD, "price": 101.0}, RECEIPT, source="constructed-test")
        self.assertEqual(first["observation_id"], repeat["observation_id"])
        self.assertTrue(repeat["exact_repeat"])
        self.assertNotEqual(changed["observation_id"], first["observation_id"])
        state = snapshot(self.db)
        self.assertEqual(len(state["observations"]), 2)
        self.assertEqual(len(state["deliveries"]), 3)
        self.assertEqual(state["revisions"], [])

    def test_explicit_revision_preserves_prior_evidence(self):
        first = record(self.db, PAYLOAD, RECEIPT)
        record(self.db, {**PAYLOAD, "price": 101.0}, RECEIPT,
               revision_of=first["observation_id"], revision_evidence="Constructed test correction marker")
        state = snapshot(self.db)
        self.assertEqual(len(state["revisions"]), 1)
        self.assertEqual([json.loads(row["payload_json"])["price"] for row in state["observations"]], [100.0, 101.0])

    def test_late_arrival_and_source_order_remain_distinct(self):
        record(self.db, PAYLOAD, RECEIPT)
        record(self.db, {**PAYLOAD, "time": "1794234540000"}, "2026-11-09T14:30:02Z")
        self.assertEqual([r[0] for r in self.db.execute("SELECT observation_id FROM observations ORDER BY source_time_ms,observation_id")], [2, 1])
        self.assertEqual([r[0] for r in self.db.execute("SELECT observation_id FROM deliveries ORDER BY receipt_id")], [1, 2])

    def test_invalid_revision_rolls_back_atomically(self):
        record(self.db, PAYLOAD, RECEIPT)
        before = snapshot(self.db)
        with self.assertRaises(ValueError):
            record(self.db, {**PAYLOAD, "price": 101}, RECEIPT, revision_of=1)
        self.assertEqual(snapshot(self.db), before)

    def test_new_backend_process_reopens_same_records(self):
        env = {**os.environ, "MARKET_DB_PATH": str(self.path)}
        messages = [{"payload": payload, "receipt_time": RECEIPT}
                    for payload in [PAYLOAD, PAYLOAD, {**PAYLOAD, "price": 101.0}]]
        subprocess.run([sys.executable, "-m", "backend.recorder", "record-test"],
                       input="\n".join(map(json.dumps, messages)), text=True,
                       env=env, cwd=ROOT, check=True, capture_output=True)
        before = snapshot(self.db)
        self.db.close()
        result = subprocess.run([sys.executable, "-m", "backend.recorder", "snapshot"],
                                env=env, cwd=ROOT, check=True, text=True, capture_output=True)
        self.db = connect(self.path)
        self.assertEqual(json.loads(result.stdout), before)
        self.assertEqual(snapshot(self.db), before)

    def test_receiver_callback_commits_before_reporting_success(self):
        from backend.feed_probe import probe

        class ConstructedSocket:
            async def __aenter__(self):
                return self

            async def subscribe(self, symbols):
                pass

            async def listen(self, callback):
                callback(PAYLOAD)
                await asyncio.sleep(10)

            async def close(self):
                pass

        output = io.StringIO()
        with patch.dict(os.environ, {"MARKET_DB_PATH": str(self.path)}), \
                patch("yfinance.AsyncWebSocket", return_value=ConstructedSocket()), redirect_stdout(output):
            result = asyncio.run(probe("AAPL", 2))
        self.assertEqual(result, 0)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        observation = next(event for event in events if event["event"] == "observation")
        self.assertEqual(observation["stored"]["observation_id"], snapshot(self.db)["observations"][0]["observation_id"])
        self.assertTrue(events[-1]["persisted"])


if __name__ == "__main__":
    unittest.main()
