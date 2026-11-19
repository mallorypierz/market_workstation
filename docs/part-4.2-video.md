# Part4.2 actual-app demonstration

Published implementation/evidence [8565d23](https://github.com/mallorypierz/market_workstation/commit/8565d239f94a356f91cbd47054e416e8bc465345); [remote CI](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) **success**; [59-second video](https://raw.githubusercontent.com/mallorypierz/market_workstation/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part-4.2-demo.webm) verified by unauthenticated full download and matching SHA256. The exact committed checkout passed tests/build/browser checks with reused local dependencies. Student review and Canvas upload remain the student’s actions.

**Recorded locally:59.00seconds,1440×1000WebM, silent with readable narration captions.** [Local recording](evidence/part-4.2-demo.webm) · [measured duration](evidence/part42-submission/duration.json) · [hash/size manifest](evidence/part42-submission/video-manifest.json).

**Public instructor-accessible URL:** [59-second demonstration](https://raw.githubusercontent.com/mallorypierz/market_workstation/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part-4.2-demo.webm). The complete file returned HTTP200 without credentials and its hash matched the locally played/measured video. The old112second Part4.1 recording is not the submitted Part4.2 video.

## Script and observed recording

| Time | Actual app view / narration |
|---|---|
|0–15s|Two Python SMA lines (2/3), UP/DOWN markers on an explicitly **constructed** receipt fixture. State that it is simulated correctness data, not live Yahoo.|
|15–23s|Expand up decision:16/13queues buy, later receipt fills1@$100. Down4/9closes on later$110. Show linked order/fill IDs/timestamps.|
|23–30s|Show account$1,010cash/equity,flat,$10realized/$0unrealized. This synthetic profit checks arithmetic only.|
|30–36s|Load saved **real Yahoo daily** result;33evaluation bars,10fills,$999.64equity,−0.036%return,1.2997%drawdown.|
|36–45s|Show historical equity curve, then historical decision/trade table.|
|45–50s|Open frozen provenance/assumptions: known at close,next supplied open execution,zero fees/slippage,dividends excluded,no forced liquidation.|
|50–56s|State causal-prefix/unfinished-candle checks and one-stock/short-sample limitation; historical results do not establish future performance.|

The assistant operated actual Vue/FastAPI with isolated saved runs. Captions are narration overlays, not fabricated results or replacement UI. No audio/model/provider call was used. The demo seeds the known constructed example and runs the same saved Yahoo daily evaluation with unchanged2/3parameters. It shows persisted results rather than claiming a new live capture. Local working databases/services were removed/stopped afterward. The new-run form can retain a different draft selection while loading a saved run; the displayed run ID and expanded frozen metadata identify the saved result being shown.

## Reproduce or replace

Use the existing installed environment; do not install packages without approval:

```sh
python3 docs/part42_video.py
DEMO_OUT="$PWD/test-results/part42-video" node frontend/tests/part42-video-inspect.mjs
```

The first command launches isolated normal FastAPI/Vue and records the real application with installed Playwright. The second loads the WebM in Chromium, reads its actual media duration and decodes representative frames. The final container duration is59.00s, measured from the encoded file rather than the script wall time. Sample frames at8/19/27/36/38/42/46/53seconds are checked; see evidence/part42-submission/. The first capture measured56.00s. After improving trade-row visibility, the revised capture measured60.92s and correctly failed the duration assertion. The installed bundled FFmpeg trimmed only trailing footage with `-t 59 -c copy`; Chromium then measured59.00s and confirmed the closing limitation remains visible. Its limited build lacks the null output muxer, so Chromium metadata/seeking provided completed verification. No source prices/results were edited. Reproduced captures must be measured; if over60s, trim trailing footage only when all required scenes remain.

For a student-operated replacement: start the app per README, create/load the isolated constructed result and saved Yahoo daily run, follow the timing table, keep captions/narration and provenance readable, hide unrelated tabs/account identifiers, stop recording by60seconds, and remeasure the final exported file. Do not edit performance figures or tune windows for a positive result.

## Publication verification

Student authorized commit/push. Implementation/evidence SHA `8565d239f94a356f91cbd47054e416e8bc465345` is public. [Access evidence](evidence/part42-submission/public-access.json) records25unauthenticated HTTP200resources with byte hashes matching local files, including the complete video. [CI evidence](evidence/part42-submission/remote-ci.json) records success for this exact SHA. The report now pins its one video and supporting links to that commit. A later documentation-only commit records the final report; the student uploads only report.md to Canvas.
