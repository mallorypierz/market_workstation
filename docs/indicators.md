# Named chart indicators

The student explicitly authorized a shared indicator interface and named rolling range/SMA instances after the original Part 4.1 scope. This adds no dependencies. Python owns calculation and validation; Vue displays the catalog, submits settings, draws returned series, and inspects values. The supplied prompt 09b is reused unchanged.

## Calculation contract

`backend/indicators.py` provides `REGISTRY`, `catalog()`, `exact_values(type, candles, status, settings)` and `calculate(...)`. Inputs are the existing six-field candle rows, completion metadata, and validated settings. Rows represent one symbol/source/interval, already selected for the current live/history/replay knowledge boundary. They are sorted by UTC candle-start timestamp. Revisions must have been resolved upstream; no duplicate current candle timestamp is expected.

Settings contain exactly `{"window": N}`, where N is a positive Python integer (not boolean, string, fraction or zero). Each instance receives its own copied settings. Only `status[timestamp].complete == true` contributes to a window: ended but partially covered intervals and still-forming candles are excluded. Windows span the last N completed candles available in the selected range, including across sessions; no missing candles or pre-range warm-up are invented.

Output is one `{timestamp, value}` per input candle. Before N completed candles exist, value is null; at an incomplete candle it is also null. Zero is a valid value and never a warm-up gap. The candle's original UTC timestamp is retained. Calculations use exact fractions from the stored decimal representations; JSON output is numeric and the Vue inspector rounds only for display. Units follow source price units (for AAPL, USD per share); range is a price difference, not percent, volume, or an annualized value.

| Type | Required candle fields | Formula | Display |
| --- | --- | --- | --- |
| `sma` | close | Sum of N completed closes / N | Price pane |
| `rolling_range` | high, low | Maximum high − minimum low over N completed candles | Separate range pane |

`backend/sma.py` now calls the same `exact_values('sma', ...)` interface twice for the existing short/long pair. Its tie-preserving crossover comparison stays exact. Named SMA instances are independently configurable single lines, not additional crossover pairs. The legacy pair controls remain session-only; named instances are saved.

## Add another type

For another rolling scalar indicator using a positive integer window, implement a pure reducer taking the N completed rows and returning an exact numeric value, then add an `IndicatorType(label, inputs, units, pane, reducer)` entry to REGISTRY. Add formula, warm-up, completion and replay tests. The catalog, validation, persistence and Vue instance picker then use that type without another endpoint or Vue calculation branch. Settings beyond this window contract, multiple outputs or new display-unit groups require an explicit schema/UI extension; they are not silently accepted. Do not let calculations access the live clock, future receipts or mutable shared state.

Every authoritative history/replay/WS view runs the configured instances after candle aggregation. Replay's original receipt prefix and correction evidence filtering therefore precede indicators. Late observations and identified revisions recompute affected windows at the step they become known. Vue replaces series data; it never combines two instance settings or accumulates stale results from another selected chart.

## HTTP and persistence

- `GET /api/indicator-types`: type keys, labels, inputs, units, pane hint, window schema/default, completion and output descriptions.
- `GET /api/indicators?symbol=AAPL&source=yahoo&timeframe=1m`: saved instances for that chart.
- `POST /api/indicators`: body `{symbol, source, timeframe, name, type, settings}`; returns the saved instance with durable ID (201). Invalid settings/type/name or duplicate chart name return 422. Storage failures return 503.
- History metadata, replay and WebSocket snapshots include an `indicators` array with each instance's ID, name, type, settings, units, pane and timestamped values. The six candle fields remain unchanged.

Names are trimmed, 1–80 characters, and unique within symbol/source/timeframe. Instances on different charts are independent. The application is local/single-user; it has no account/workspace sharing or deployment. Select the same symbol and interval to reopen that chart's saved instances. Browser refresh starts at the existing default AAPL/1m; chart navigation state is not persisted. Adding an indicator reloads the selected view and restarts replay. Editing/removing saved instances is not implemented in this task.

Settings are in a separate SQLite database, default `backend/data/chart-settings.sqlite3`, configurable with `MARKET_SETTINGS_DB_PATH`. Relative paths resolve under the project root. The first valid POST creates the file/table idempotently; GET does not create an absent file. It is independent of MARKET_DB_PATH, so saving chart preferences does not write to recorded market observations or receipt/revision history. Both files and SQLite sidecars are already ignored by Git.

```sql
CREATE TABLE indicator_instances (
  id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  source TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  settings_json TEXT NOT NULL,
  UNIQUE(symbol, source, timeframe, name)
);
```

Validate before creating/writing; parameterized inserts commit transactionally. Invalid writes preserve existing instances. Reads reopen the settings database, so a fresh page/backend process sees the same saved configuration. Catalog type keys are stable persistence identifiers; removing a type needs an explicit migration.

## Repeatable verification

```sh
python3 -m unittest backend.test_indicators backend.test_sma -v
```

Constructed fixture helper creates a separate observation database (prints its folder):

```sh
python3 - <<'PY'
from pathlib import Path
import tempfile
from backend.recorder import connect
from backend.test_indicators import seed_range
folder = Path(tempfile.mkdtemp(prefix='range-fixture-'))
db = connect(folder / 'observations.sqlite3')
seed_range(db)
db.close()
print(folder)
PY
```

Set both paths to that printed folder, use the explicit label, disable Yahoo, and start the normal frontend:

```sh
MARKET_DB_PATH=/printed/folder/observations.sqlite3 MARKET_SETTINGS_DB_PATH=/printed/folder/settings.sqlite3 MARKET_DATA_LABEL='CONSTRUCTED rolling range fixture — not Yahoo data' MARKET_FEED_ENABLED=0 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio
npm --prefix frontend run dev
```

In localhost:5173 choose Rolling price range, name Range 2/window2, then Range 3/window3. Inspect 2026-11-09 14:32 UTC: 5 and6. Refresh and verify both rows return. Try a new name with window0: clear error, both rows unchanged. Stop services with Ctrl+C. The fixture uses six labeled price messages to create three high/low pairs (12,9),(15,10),(13,11). It is not a Yahoo capture. See [verification](verification.md), [API/SQLite evidence](evidence/range-check.json) and [browser screenshot](evidence/range-indicators.png).
