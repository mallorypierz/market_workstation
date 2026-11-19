# Completed-candle SMA

The student explicitly authorized this two-SMA extension on 2026-11-15. The November 17 Part 4.2 request authorizes focused SMA verification; other existing extensions retain their separately documented authorizations. No new dependencies are required. Python computes both lines and confirmed signals; Vue only converts timestamps, plots values/markers, and formats numbers to six decimal places for inspection.

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


## Part 4.2 independent reference and browser verification

On November 17, 2026, the existing production SMA and Vue chart passed the expanded checks without a production calculation change. Reused prompt09a. Run:

```sh
python3 -m unittest backend.test_sma backend.test_indicators backend.test_replay -v
python3 docs/sma_check.py
```

The second command uses already installed Playwright/Chromium, isolated localhost FastAPI/Vue services, a disposable seven-candle SQLite fixture and separate indicator settings. It disables Yahoo, removes the model key from child environments, calls no provider, and stops owned processes/browser. It installs nothing. Current-run logs, reference JSON, browser assertions and screenshots are overwritten under ignored `test-results/sma/`; curated November17 copies are linked below.

### Reference provenance and independence

[backend/sma_reference.py](../backend/sma_reference.py) is a test oracle built from Python's bundled SQLite (checked3.45.3), using SQL integer `SUM`/`COUNT` window frames. It imports neither the production SMA nor indicator module. Dataset1 is the assignment's seven hand-worked closes; dataset2 is a fixed, authored synthetic30-bar series, not downloaded market data:

`10,10,10,10,10,13,16,19,16,13,10,7,4,7,10,13,16,19,22,19,16,13,10,7,10,13,16,19,16,13`

For window N, the oracle emits `SUM(last N completed closes)/N` only when the SQL frame count equals N. It compares integer cross-products `short_sum × long_window − long_sum × short_window`; no floating-point rounding determines side. For each row, it searches earlier nonzero comparisons to identify a side change, independently of the production side-state implementation. This is an independent reference calculation anchored to the assignment arithmetic, not a claim of third-party certification. The oracle intentionally accepts only integer closes; the existing tiny-decimal precision test independently verifies production behavior below display precision.

Expected and observed JSON means use the same final numeric representation; tolerance is **zero** for these fixtures, with exact timestamp/null/signal equality. This does not imply arbitrary live floating-point inputs retain their original precision. [Full expected/observed values for both datasets](evidence/sma-part42-reference.json) include every warm-up gap.

| Seven-bar close | Short2 | Long3 | Confirmed signal |
| --- | --- | --- | --- |
| 13 | unavailable | unavailable | none |
| 10 | 11.5 | unavailable | none |
| 7 | 8.5 | 10 | none: first comparable side |
| 13 | 10 | 10 | none: retain below |
| 19 | 16 | 13 | up |
| 7 | 13 | 13 | none: retain above |
| 1 | 4 | 9 | down |

For the30-bar series with windows3/5, bars1–2 have neither mean, bars3–4 only short, and the first comparable bar5 is a tie. Bar6 establishes above with no signal. Crossovers occur at one-based bars11/down,16/up,22/down and27/up. The last bar30 has short16/long15.4 and no new signal. See the linked JSON for all30 rows.

### Meaning of incremental and causal checks

Incremental here means **recompute the available receipt prefix** after each new observation, not a separate stateful rolling accumulator. Tests compare every prefix0–7 and0–30 with the independently expected completed-candle batch prefix, including warm-up. When a correction or late arrival changes an earlier candle, the correct comparison is a fresh reference over the data known at that step, not a prefix of finally corrected history.

Expanded tests cover an absent minute (no fabricated close), exact duplicate delivery (no extra SMA sample), a late arrival filling that gap, an explicitly linked correction, and unchanged earlier views after all future events are stored. They test an incomplete5-minute candle before gap repair and a complete5-minute candle afterward that still lacks SMA warm-up. Interleaved AAPL and supported SAMPLE-symbol Yahoo-shaped **constructed** observations verify symbol isolation; alternating1m/5m requests and returning to the original view verifies timeframe isolation. Existing tests retain initial ties, exact sub-display differences, invalid windows and unfinished/ended-but-incomplete suppression. No provisional SMA values are displayed: incomplete rows stay unavailable and cannot confirm a crossover.

### Actual browser results

The focused runner checked the seven replay prefixes through real HTTP responses and every selected-candle value in Vue. It checked both confirmed crossover entries, zero/fraction/equal/reversed input rejection, server422 validation, and a valid change to3/5 clearing stale markers and restarting replay. No browser page errors occurred. Agent visual inspection of the screenshot confirmed the blue short line, purple long line, their distinct warm-up starts, green up marker at14:34 and red down marker at14:36.

[Chart screenshot](evidence/sma-part42-chart.png) · [full browser screenshot](evidence/sma-part42-page.png) · [browser assertions and prefix results](evidence/sma-part42-browser.json) · [runner result/cleanup](evidence/sma-part42-result.json). These are synthetic correctness observations, not live Yahoo or backtest performance evidence.
