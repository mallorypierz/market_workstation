# Completed-candle SMA

The student explicitly authorized this two-SMA extension on 2026-11-15. Other later-part features are not authorized. No new dependencies are required. Python computes both lines and confirmed signals; Vue only converts timestamps, plots values/markers, and formats numbers to six decimal places for inspection.

`backend/sma.py` decorates each already-selected candle view. HTTP history with `include_metadata=true`, live WebSocket snapshots, and replay responses include `sma: {short_window, long_window, values}` separately from the unchanged six candle fields. Query parameters `short` and `long` default to 2 and 3. HTTP rejects invalid values with 422; WebSocket rejects invalid window ordering with close code 1008. UI validates positive whole numbers and short < long. Apply SMA windows reloads the selected symbol/timeframe and restarts replay.

A completed candle means existing backend `status[timestamp].complete == true`: its interval has ended and expected minute coverage is present. An ended but partially covered higher-timeframe candle is excluded. This is the existing coverage model, not a claim that the provider delivered every trade. Missing intervals are not filled. Windows span the last N available completed candles, including across sessions, within the selected history/replay range; no hidden pre-range warm-up is fetched.

Every returned candle has an SMA row; an unfinished/incomplete candle has null averages and no confirmed signal. For completed candles, each window independently warms up. Python constructs exact `Fraction` values from the available decimal closing-price representation and compares them before any float/JSON/display rounding. This cannot restore precision already lost when source prices entered storage. Ties retain the last non-equal side; initial equality leaves the side unset. The first non-equal comparable pair establishes it without a signal. Only a switch between above and below emits up/down.

Each view is recomputed, with no signal state shared across symbols, timeframes, clients or windows. Replay filters original receipts and explicit revisions before candle aggregation and SMA. Thus future observations/corrections cannot enter earlier steps. When a late correction becomes known, the affected candle and subsequent averages/signals are replaced in the authoritative view. Vue replaces lines and marker lists, removing obsolete markers rather than accumulating duplicates. Replay completion fits the entire selection so both markers remain visible.

Chart API references checked against installed Lightweight Charts 5.3.0 and official 5.3 documentation: [line series](https://tradingview.github.io/lightweight-charts/docs/series-types), [createSeriesMarkers](https://tradingview.github.io/lightweight-charts/docs/api/functions/createSeriesMarkers). No chart package changes.

## Repeatable reference check

```sh
python3 -m unittest backend.test_sma -v
```

This creates a disposable database, records seven explicitly constructed AAPL-shaped messages with closes 13,10,7,13,19,7,1, and compares the full calculation with every original-receipt replay prefix. Each test receipt is at the next minute boundary, so that candle is complete when first revealed. Other tests cover unfinished/incomplete candles, identified revisions, validation, initial ties and differences smaller than display precision. Test data never enters the actual captured database.

To recreate the browser fixture (prints a separate temporary DB path):

```sh
python3 - <<'PY'
import tempfile
from pathlib import Path
from backend.recorder import connect
from backend.test_sma import seed
path = Path(tempfile.mkdtemp(prefix='sma-reference-')) / 'constructed.sqlite3'
db = connect(path)
seed(db)
db.close()
print(path)
PY
```

Use the printed absolute path for MARKET_DB_PATH, then run the normal local frontend:

```sh
MARKET_DB_PATH=/absolute/path/printed/above/constructed.sqlite3 MARKET_DATA_LABEL='CONSTRUCTED SMA test data — not a Yahoo capture' MARKET_FEED_ENABLED=0 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
npm --prefix frontend run dev
```

Open localhost:5173, inspect batch history, select Replay, then Next observation seven times. Expect the table in verification.md, two markers at 14:34 and 14:36 UTC on November 9, and the constructed-data banner. Stop both services with Ctrl+C. Do not start Yahoo against this fixture. Normal startup omits MARKET_DATA_LABEL and the temporary MARKET_DB_PATH.
