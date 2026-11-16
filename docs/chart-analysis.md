# Ask about chart

The student selects a completed AAPL candle and clicks **Ask about chart**. The dashboard freezes symbol, interval, visible range ending at that candle, paired SMA windows and the selected paper account. Dropdown selections stay pinned until **Use hover selection** or a chart reload. In replay, start a replay paper account first and advance it through the cutoff; receipt limits and account-origin checks still apply.

The backend creates the immutable decision snapshot before rendering or analysis. It calculates candles and SMAs from the same historical receipt/revision boundary as the prior decision API. Named indicator definitions and calculated values are also saved. Full preceding history is used for calculation, then the saved chart is restricted to the selected visible range. Later candles never enter the capture. The last candle's timestamp is its interval start; the displayed **cutoff** is its exclusive interval end.

Vue creates a separate fixed chart from the saved records: candlesticks, aligned volume pane, paired SMA lines and named indicator lines. Unknown volume stays a gap; it is never fabricated. A neutral marker identifies the selected cutoff rather than drawing the answer to the crossover question. The preview includes symbol, interval, range, cutoff, data provenance, account facts and all three questions. Live updates continue on the main chart without changing this PNG. **Analyze frozen chart** sends the reviewed capture once; recapture creates a new snapshot. The export contains only chart pixels, including its scales and attribution, not page controls/account credentials.

## Capture and request contract

[Lightweight Charts' official screenshot example](https://tradingview.github.io/lightweight-charts/examples/data/screenshot) documents `chart.takeScreenshot()` and canvas PNG export. The installed5.3.0 library is reused. The frontend renders a1000×560 CSS-pixel chart; its exported pixel dimensions follow device pixel ratio (the observed capture was2000×1120).

The PNG contains a `market_snapshot` tEXt chunk with snapshot_id, snapshot SHA-256 and chart_range. POST `/api/decisions` receives `analysis:"chart"`, that snapshot_id, snapshot_sha256, chart_range and the `data:image/png;base64,...` image. Python reloads the snapshot from SQLite, checks these bindings, verifies PNG signature/chunk checksums/end marker, bounded dimensions, decompression and all RGB/RGBA row filters, and rejects blank/truncated/unsupported images. No Pillow or other package was installed. Supported exports are noninterlaced8-bit RGB/RGBA,320–2400px wide and200–1600px high, under6MB. On an unsupported high-DPI export the UI asks for recapture; use a lower browser/device scaling setting.

The PNG binding catches accidental swaps and changed snapshot IDs/ranges. It is not a cryptographic proof that arbitrary client pixels depict the records: a malicious client could forge metadata. Model visual assessment is a claim, not an independent trusted price calculation. All execution remains disabled for this analysis workflow; tests are always order-ineligible.

The [official OpenAI request reference](https://developers.openai.com/api/reference/resources/decisions/methods/create) defines input_json.data and data-URL input_image. Python sends **one user message** with both:

```json
{"role":"user","content":[
  {"type":"input_json","data":{"snapshot_id":"...","chart":"saved records and other snapshot facts"}},
  {"type":"input_image","image_url":"data:image/png;base64,..."}
]}
```

The actual request includes the full saved snapshot, not the abbreviated example above. Three choice questions share that input:

| Name | Allowed answers |
| --- | --- |
| action | buy, sell, hold, wait, close |
| crossover | up, down, none, unreadable |
| evidence | sufficient, insufficient, unreadable |

`GET /api/chart-questions` exposes the exact server questions displayed in Vue. Answers are validated by unique name rather than response order. Missing, duplicate, unknown, malformed or refused answers fail validation. Action uses frozen cash/shares/configured size. Crossover is compared with Python's exact SMA logic. Unreadable images, insufficient evidence or conflicting signals always set order_eligible=false and show recapture guidance. Existing text-only decisions remain supported when no image analysis is requested.

## Durable evidence

`decision_images` stores decision_id (primary key/FK), snapshot_id, PNG BLOB, SHA-256, width, height and questions_json. `decisions.result_json` stores questions, named answers, backend comparison, status, explanation, image retrieval URL and frozen cutoff/range. `GET /api/decisions/{id}/image` returns the original PNG. Invalid image bytes are rejected rather than stored as a valid capture; the decision still records failure status and recapture reason. Valid bytes remain retrievable even if the provider fails.

PNG storage is inside the ignored MARKET_DB_PATH SQLite file; no key is included. Neither freeze nor analysis calls paper.execute. No browser mechanism selects the mock provider: the test app installs an in-process provider double, while normal backend.main uses the real backend environment key.

## Supervised browser SmokeTest

One startup command from the root:

```sh
python3 -m backend.chart_smoke
```

It prints a new disposable database path and starts localhost5174/8010 with Yahoo disabled, an isolated indicator settings path, synthetic recorded closes and the controlled provider. It removes OPENAI_API_KEY from the test child environment. No source edits or installations are required. In a browser:

1. Open http://127.0.0.1:5174/ and choose2026-11-09 14:34 UTC in Inspect candle.
2. Click Ask about chart. Confirm AAPL/1m, cutoff14:35 UTC, chart range ending14:34, short SMA16 and long SMA13, and synthetic-data labeling.
3. Inspect the PNG and the three questions; click Analyze frozen chart.
4. Expect buy/up/sufficient, Python up, no order created and test-data execution eligibility no. Changing the main chart afterward must leave this preview unchanged.
5. Compare the stored evidence (substitute the printed database path):

```sh
python3 -m backend.chart_check --source-db /absolute/fixture.sqlite3 --png-output /private/tmp/chart-smoke-capture.png
```

This decodes the actual browser PNG, compares its bytes/hash and snapshot with the test provider's recorded input, reads the persisted answers and asserts zero orders. Ctrl+C in the startup terminal stops both test services. This is a **supervised** SmokeTest; do not claim automated browser coverage when only the unit tests ran.

For one separately labeled live image request, first run the documented key-bearing backend on localhost8001 with `/private/tmp/market-decisions-live-check.sqlite3`. Then:

```sh
python3 -m backend.chart_check --source-db /absolute/fixture.sqlite3 --live-db /private/tmp/market-decisions-live-check.sqlite3 --png-output /private/tmp/chart-smoke-capture.png
```

This fixture-only check imports the exact immutable test snapshot into that disposable database and sends the original PNG unchanged. It makes one provider request, compares its saved response/image, and checks all six paper tables unchanged. It does not recapture, relabel the PNG or send a fabricated chart. Live model access and synthetic market data are separate facts. See [observed results and initial failure](verification.md).

## Limitations

AAPL/current supported intervals only. Too-short visible ranges can legitimately receive insufficient evidence. The fixture uses one observation per minute, so its candlesticks are flat dojis and its volume is unknown; the SMA crossover remains visible. Large source snapshots can exceed the provider's JSON limits and return provider_error; no hidden truncation is applied. The model sees both chart and backend facts, so agreement alone does not prove independent visual reasoning. No automated order dispatch, chart-question editing or image upload from arbitrary files was added.

## Subsequent reviewer extension

Image analysis now also makes one reviewer call after a structurally valid analyst proposal. It receives the same PNG, snapshot and actual analyst named answers. The controlled SmokeTest provider supplies a separate accept reply for review; normal service uses the configured provider. One endpoint request may therefore make two model calls. See [review rules and trace](decision-review.md); earlier one-call evidence describes the version tested at that time.
