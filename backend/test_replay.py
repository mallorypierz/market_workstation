"""Constructed late arrivals/corrections in a separate temporary database."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime

from backend.recorder import connect, record
from backend.replay import replay_view, recordings


def payload(source, price):
    return {"id":"AAPL", "time": str(int(datetime.fromisoformat(source.replace("Z", "+00:00")).timestamp()*1000)), "price":price}


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)/"constructed.sqlite3"
        self.env = patch.dict(os.environ, {"MARKET_DB_PATH":str(self.path)})
        self.env.start()
        self.db = connect(self.path)
        record(self.db,payload("2026-11-09T14:30:05Z",100),"2026-11-09T14:30:06Z")
        record(self.db,payload("2026-11-09T14:30:50Z",101),"2026-11-09T14:30:51Z")
        middle=record(self.db,payload("2026-11-09T14:30:20Z",103),"2026-11-09T14:31:01Z")
        record(self.db,payload("2026-11-09T14:30:20Z",104),"2026-11-09T14:31:02Z",
               revision_of=middle["observation_id"],revision_evidence="CONSTRUCTED correction")

    def tearDown(self):
        self.db.close();self.env.stop();self.folder.cleanup()

    def view(self, step, **kwargs):
        return replay_view(symbol="AAPL",start="2026-11-09T14:30:00Z",end="2026-11-09T14:32:00Z",step=step,**kwargs)

    def test_late_arrival_revision_and_repeat(self):
        self.assertEqual(self.view(0)["candles"],[])
        self.assertEqual(self.view(2)["candles"][0]["high"],101)
        late=self.view(3)
        self.assertEqual(late["candles"][0]["high"],103)
        self.assertEqual(late["candles"][0]["close"],101)
        self.assertEqual(late["feed"]["latest"]["source_time"],"2026-11-09T14:30:20Z")
        revised=self.view(4)
        self.assertEqual(revised["candles"][0]["high"],104)
        self.assertEqual(revised["candles"][0]["close"],101)
        self.assertIsNone(revised["candles"][0]["volume"])
        record(self.db,payload("2026-11-09T14:30:20Z",104),"2026-11-09T14:31:03Z")
        self.assertEqual(self.view(5)["candles"],revised["candles"])
        self.assertEqual(self.view(5,snapshot_cutoff=4),revised)

    def test_two_runs_are_identical_and_read_only(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        first=[self.view(i) for i in range(5)]
        second=[self.view(i) for i in range(5)]
        self.assertEqual(first,second)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],4)

    def test_empty_and_exclusive_boundary(self):
        empty=replay_view(symbol="AAPL",start="2026-11-10T00:00:00Z",end="2026-11-11T00:00:00Z",step=1)
        self.assertTrue(empty["replay"]["empty"])
        self.assertEqual(empty["candles"],[])
        view=replay_view(symbol="AAPL",start="2026-11-09T14:30:06Z",end="2026-11-09T14:30:51Z",step=10)
        self.assertEqual(view["replay"]["total"],1)
        self.assertEqual(view["candles"][0]["close"],100)
        self.assertEqual(recordings()[0]["symbol"],"AAPL")

    def test_receipt_sequence_survives_clock_regression(self):
        record(self.db,payload("2026-11-09T14:30:10Z",99),"2026-11-09T14:30:30Z")
        view=self.view(5)
        self.assertEqual(view["feed"]["latest"]["receipt_id"],5)
        self.assertEqual(view["as_of"],"2026-11-09T14:31:02Z")
        self.assertEqual(view["candles"][0]["low"],99)
