"""Constructed assignment data only; these tests do not verify Yahoo volume."""
from datetime import datetime
import tempfile
from pathlib import Path
import unittest

from backend.candles import aggregate
from backend.recorder import connect, record, snapshot

MINUTE = "2026-11-09T15:00:00Z"
EXPECTED = dict(timestamp=MINUTE, open=100, high=103, low=100, close=101, volume=11)
SAMPLES = [("14:59:59", 99, 1000), ("15:00:05", 100, 1004),
           ("15:00:20", 103, 1009), ("15:00:50", 101, 1011)]


class CandleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.folder.name) / "test.sqlite3")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def add(self, time, price, total, **kwargs):
        stamp = datetime.fromisoformat("2026-11-09T" + time + "+00:00")
        payload = {"id": "AAPL", "time": str(int(stamp.timestamp() * 1000)), "price": price}
        if total is not None:
            payload["day_volume"] = str(total)
        return record(self.db, payload, "2026-11-09T15:01:05Z", source="constructed-test", **kwargs)

    def result(self, as_of="2026-11-09T15:01:00Z", **kwargs):
        return aggregate(self.db, "AAPL", source="constructed-test", as_of=as_of,
                         cumulative_volume_field="day_volume", **kwargs)

    def candle(self, result):
        return next(c for c in result["candles"] if c["timestamp"] == MINUTE)

    def test_assignment_before_and_at_end_duplicate(self):
        for sample in SAMPLES:
            self.add(*sample)
        self.add(*SAMPLES[2])
        before = self.result("2026-11-09T15:00:59.999Z")
        after = self.result()
        self.assertEqual(self.candle(before), EXPECTED)
        self.assertEqual(self.candle(after), EXPECTED)
        self.assertFalse(before["status"][MINUTE]["ended"])
        self.assertTrue(after["status"][MINUTE]["ended"])
        self.assertEqual(len(after["status"][MINUTE]["observation_ids"]), 3)

    def test_late_middle_updates_ended_candle_and_replay(self):
        for index in [0, 1, 3]:
            self.add(*SAMPLES[index])
        before = self.result()
        self.assertEqual(self.candle(before)["high"], 101)
        self.add(*SAMPLES[2])
        self.assertEqual(self.candle(self.result()), EXPECTED)
        self.assertEqual(self.result(receipt_cutoff=3), before)

    def test_missing_baseline_reset_missing_total(self):
        for sample in SAMPLES[1:]:
            self.add(*sample)
        self.assertIsNone(self.candle(self.result())["volume"])
        self.add(*SAMPLES[0])
        self.assertEqual(self.candle(self.result())["volume"], 11)
        self.add("15:00:55", 102, 2)
        result = self.result()
        self.assertIsNone(self.candle(result)["volume"])
        self.assertIn("cumulative_total_reset", result["status"][MINUTE]["volume_reasons"])
        self.add("15:01:05", 103, 4)
        recovered = self.result("2026-11-09T15:01:06Z")
        self.assertEqual(recovered["candles"][-1]["volume"], 2)
        self.add("15:01:10", 104, None)
        self.assertIsNone(self.result("2026-11-09T15:01:11Z")["candles"][-1]["volume"])

    def test_identified_correction_recomputes_without_erasing_evidence(self):
        ids = [self.add(*sample) for sample in SAMPLES]
        before = self.result()
        self.add("15:00:20", 104, 1009, revision_of=ids[2]["observation_id"], revision_evidence="CONSTRUCTED correction")
        after = self.result()
        self.assertEqual(self.candle(after), {**EXPECTED, "high": 104})
        self.assertEqual(self.result(receipt_cutoff=4), before)
        self.assertEqual(len(snapshot(self.db)["observations"]), 5)

    def test_ambiguous_same_time_preserves_prices_and_marks_volume_unknown(self):
        for sample in SAMPLES:
            self.add(*sample)
        self.add("15:00:20", 104, 1009)
        result = self.result()
        self.assertEqual(self.candle(result)["high"], 104)
        self.assertIsNone(self.candle(result)["volume"])
        self.assertEqual(len(result["status"][MINUTE]["observation_ids"]), 4)

    def test_boundaries_ticker_source_and_no_semantics(self):
        self.add("15:00:00", 100, 1000)
        self.add("15:01:00", 101, 1011)
        self.assertEqual(len(self.result()["candles"]), 2)
        self.assertFalse(self.result()["status"]["2026-11-09T15:01:00Z"]["ended"])
        result = aggregate(self.db, "AAPL", source="constructed-test", as_of="2026-11-09T15:01:00Z")
        self.assertTrue(all(c["volume"] is None for c in result["candles"]))
        self.assertEqual(aggregate(self.db, "MSFT", source="constructed-test", as_of=MINUTE)["candles"], [])
        self.assertEqual(aggregate(self.db, "AAPL", as_of=MINUTE)["candles"], [])
        with self.assertRaises(ValueError):
            self.result("2026-11-09T15:01:00")

    def test_yahoo_default_counter_estimate_and_duplicate(self):
        for time, price, total in SAMPLES:
            stamp = datetime.fromisoformat("2026-11-09T" + time + "+00:00")
            payload = {"id": "AAPL", "time": str(int(stamp.timestamp()*1000)),
                       "price": price, "day_volume": str(total), "last_size": "999"}
            record(self.db, payload, "2026-11-09T15:01:05Z")
        record(self.db, payload, "2026-11-09T15:01:06Z")
        view = aggregate(self.db, "AAPL", as_of="2026-11-09T15:01:10Z")
        self.assertEqual(self.candle(view), EXPECTED)
        self.assertEqual(view["status"][MINUTE]["volume_status"], "observed_delta_estimate")
        self.assertIsNone(view["candles"][0]["volume"])
        self.assertIsNone(aggregate(self.db, "AAPL", as_of="2026-11-09T15:01:10Z",
                                   receipt_cutoff=1)["candles"][0]["volume"])

    def test_session_boundary_and_long_gap(self):
        self.add("14:57:59", 99, 1000)
        self.add("15:00:05", 100, 1004)
        self.assertIsNone(self.candle(self.result())["volume"])
        self.add("23:59:59", 100, 1004)
        next_time = int(datetime.fromisoformat("2026-11-10T00:00:05+00:00").timestamp()*1000)
        record(self.db, {"id":"AAPL", "time":str(next_time), "price":101, "day_volume":"1008"},
               "2026-11-10T00:00:06Z", source="constructed-test")
        self.assertIsNone(self.result("2026-11-10T00:00:10Z")["candles"][-1]["volume"])


if __name__ == "__main__":
    unittest.main()
