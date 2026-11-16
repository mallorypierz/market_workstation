"""Constructed minute fixtures and recorded-observation replay; no live claims."""
from datetime import datetime
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.history import read_candles
from backend.recorder import connect, record
from backend.timeframes import resample, history_view

EXPECTED = {"timestamp": "2026-11-09T14:30:00Z", "open": 100, "high": 105,
            "low": 99, "close": 104, "volume": 3550}


def minute(timestamp, volume=100, price=106):
    return dict(timestamp=timestamp, open=price, high=price, low=price, close=price, volume=volume)


class TimeframeTests(unittest.TestCase):
    def view(self, rows, timeframe="5m", as_of="2026-11-12T00:00:00Z"):
        return resample(rows, timeframe=timeframe, symbol="SAMPLE", as_of=as_of)

    def test_sample_expected_and_partial_day(self):
        rows = read_candles()
        view = self.view(rows)
        self.assertEqual(view["candles"], [EXPECTED])
        status = view["status"][EXPECTED["timestamp"]]
        self.assertEqual((status["present_minutes"], status["expected_minutes"]), (3, 5))
        self.assertFalse(status["coverage_complete"])
        self.assertFalse(status["complete"])
        self.assertTrue(status["ended"])
        daily = self.view(rows, "1d")
        self.assertEqual(daily["candles"], [EXPECTED])
        self.assertEqual(daily["status"][EXPECTED["timestamp"]]["expected_minutes"], 390)

    def test_gap_second_bucket_and_next_session(self):
        rows = read_candles() + [minute("2026-11-09T14:35:00Z"), minute("2026-11-10T14:30:00Z")]
        five = self.view(rows)
        self.assertEqual([row["timestamp"] for row in five["candles"]],
                         ["2026-11-09T14:30:00Z", "2026-11-09T14:35:00Z", "2026-11-10T14:30:00Z"])
        daily = self.view(rows, "1d")
        self.assertEqual(len(daily["candles"]), 2)
        self.assertEqual(daily["candles"][0]["volume"], 3650)
        self.assertEqual(daily["status"][EXPECTED["timestamp"]]["present_minutes"], 4)

    def test_all_intervals_align_to_open_and_preserve_fields(self):
        rows = [minute("2026-11-09T15:00:00Z"), minute("2026-11-09T15:30:00Z")]
        hourly = self.view(rows, "1h")
        self.assertEqual([r["timestamp"] for r in hourly["candles"]], ["2026-11-09T14:30:00Z", "2026-11-09T15:30:00Z"])
        for timeframe in ["1m", "5m", "15m", "1h", "1d"]:
            for row in self.view(rows, timeframe)["candles"]:
                self.assertEqual(set(row), {"timestamp", "open", "high", "low", "close", "volume"})
        self.assertEqual(self.view([minute("2026-11-09T14:46:00Z")], "15m")["candles"][0]["timestamp"], "2026-11-09T14:45:00Z")

    def test_early_close_holiday_dst(self):
        early = self.view([minute("2026-11-27T17:59:00Z"), minute("2026-11-27T18:00:00Z")], "1d", "2026-11-28T00:00:00Z")
        self.assertEqual(early["status"]["2026-11-27T14:30:00Z"]["expected_minutes"], 210)
        self.assertEqual(early["excluded_outside_session"], ["2026-11-27T18:00:00Z"])
        last_hour = self.view([minute("2026-11-27T17:59:00Z")], "1h", "2026-11-28T00:00:00Z")
        self.assertEqual(last_hour["status"]["2026-11-27T17:30:00Z"]["expected_minutes"], 30)
        self.assertEqual(self.view([minute("2026-11-26T14:30:00Z")], "1d", "2026-11-28T00:00:00Z")["candles"], [])
        for stamp in ["2026-03-06T14:30:00Z", "2026-03-09T13:30:00Z", "2026-10-30T13:30:00Z", "2026-11-02T14:30:00Z"]:
            self.assertEqual(self.view([minute(stamp)], "1d")["candles"][0]["timestamp"], stamp)

    def test_unknown_zero_and_complete_coverage(self):
        rows = [minute(f"2026-11-09T14:3{i}:00Z", volume=0) for i in range(5)]
        view = self.view(rows)
        self.assertEqual(view["candles"][0]["volume"], 0)
        self.assertTrue(view["status"][EXPECTED["timestamp"]]["complete"])
        rows[2]["volume"] = None
        view = self.view(rows)
        self.assertIsNone(view["candles"][0]["volume"])
        self.assertTrue(view["status"][EXPECTED["timestamp"]]["coverage_complete"])
        self.assertFalse(view["status"][EXPECTED["timestamp"]]["volume_known_for_present_minutes"])

    def test_sample_cutoff_excludes_unfinished_csv_minutes(self):
        view = history_view(timeframe="5m", as_of="2026-11-09T14:31:00Z")
        self.assertEqual(view["candles"][0]["volume"], 1200)
        self.assertEqual(view["candles"][0]["close"], 102)
        self.assertFalse(view["status"][EXPECTED["timestamp"]]["ended"])
        self.assertEqual(history_view(as_of="2026-11-09T14:30:59Z")["candles"], [])
        with self.assertRaises(ValueError):
            history_view(symbol="AAPL")

    def test_recorded_revision_and_late_data_respect_displayed_time(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.sqlite3"
            db = connect(path)
            time = str(int(datetime.fromisoformat("2026-11-09T14:30:05+00:00").timestamp()*1000))
            first = record(db, {"id":"AAPL", "time":time, "price":100}, "2026-11-09T14:30:06Z")
            record(db, {"id":"AAPL", "time":time, "price":105}, "2026-11-09T15:00:00Z",
                   revision_of=first["observation_id"], revision_evidence="CONSTRUCTED correction")
            # Later insertion with an earlier receipt time exercises independent time/sequence checks.
            record(db, {"id":"AAPL", "time":str(int(time)+10000), "price":101}, "2026-11-09T14:30:16Z")
            db.close()
            with patch.dict(os.environ, {"MARKET_DB_PATH": str(path)}):
                before = history_view(source="yahoo", symbol="AAPL", timeframe="5m", as_of="2026-11-09T14:31:00Z")
                after = history_view(source="yahoo", symbol="AAPL", timeframe="5m", as_of="2026-11-09T15:01:00Z")
                self.assertEqual((before["candles"][0]["open"], before["candles"][0]["close"]), (100,101))
                self.assertEqual((after["candles"][0]["open"], after["candles"][0]["close"]), (105,101))
                self.assertEqual(len(after["candles"]), 1)
                limited = history_view(source="yahoo", symbol="AAPL", as_of="2026-11-09T15:01:00Z", receipt_cutoff=1)
                self.assertEqual(limited["candles"][0]["close"], 100)
                self.assertIsNone(after["candles"][0]["volume"])


if __name__ == "__main__":
    unittest.main()
