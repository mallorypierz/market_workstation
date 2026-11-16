import tempfile
import unittest
from pathlib import Path

from backend.history import FIELDS, read_candles


class HistoryTests(unittest.TestCase):
    def test_supplied_row_and_fields(self):
        candles = read_candles()
        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[1], dict(zip(FIELDS, ["2026-11-09T14:31:00Z", 102, 104, 100, 101, 850])))
        self.assertTrue(all(list(row) == FIELDS for row in candles))

    def read_fixture(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candles.csv"
            path.write_text(",".join(FIELDS) + "\n" + rows)
            return read_candles(path)

    def test_sorts_unsorted_rows(self):
        rows = self.read_fixture("2026-11-09T14:31:00Z,102,104,100,101,850\n2026-11-09T14:30:00Z,100,103,99,102,1200\n")
        self.assertEqual([row["volume"] for row in rows], [1200, 850])

    def test_rejects_ambiguous_or_invalid_rows(self):
        for row in ["2026-11-09T14:31:01Z,102,104,100,101,850\n",
                    "2026-11-09T14:31:00,102,104,100,101,850\n",
                    "2026-11-09T14:31:00Z,nan,104,100,101,850\n",
                    "2026-11-09T14:31:00Z,102,104,100,101,-1\n",
                    "2026-11-09T14:31:00Z,102,104,100,101,850\n" * 2]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.read_fixture(row)


if __name__ == "__main__":
    unittest.main()
