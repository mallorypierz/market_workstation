# Offline SmokeTest

From the project root, run one command:

```sh
python3 docs/smoke_test.py
```

It starts isolated FastAPI and Vue services on free localhost ports, waits for HTTP readiness, opens real Chromium, performs the checks below, queries SQLite independently, closes the browser and terminates owned process groups. A missing expected result returns exit1. It does not edit source, install software, run AutoLoop, or contact Yahoo/OpenAI. Each run starts new market/settings databases and a new browser context; test accounts start with $1,000. Runtime artifacts go to ignored `test-results/smoke/<UTC-run-id>/`: result JSON, SQLite copy, logs, browser evidence, final screenshot and failure trace/screenshot. Temporary working databases are removed after shutdown. The application/source databases and user-owned services are not used.

Locally Chromium is visible. In GitHub Actions, CI=true runs the same real Chromium UI headlessly. For an optional local headless run, prefix `SMOKE_HEADLESS=1`. No provider credentials are needed; OPENAI_API_KEY is removed from child environments. Browser external network requests are blocked, Yahoo start is stubbed to fail locally, and model requests are handled only by a controlled callback.

## Approved prerequisites

Python3.12 with the existing `backend/requirements.txt` environment, Node24/npm and installed frontend dependencies are required. Playwright Test1.65.1 is now pinned in frontend/package.json and package-lock.json. It and Chromium were approved and installed on this computer. No Python environment was created or changed.

For an approved restoration on another machine:

```sh
npm ci --prefix frontend
frontend/node_modules/.bin/playwright install chromium
```

This downloads a browser into the user's Playwright cache. Follow AGENTS approval rules before local installations. SmokeTest itself never downloads a browser or restores packages. CI installs the existing Python requirements, runs npm ci, then `playwright install --with-deps chromium` in its disposable runner.

Official references: [Playwright installation](https://playwright.dev/docs/intro), [browser installation](https://playwright.dev/docs/browsers), [GitHub Actions setup](https://playwright.dev/docs/ci-intro).

## Assertions

1. Open the six-observation recorded selection in Vue Replay. Add named Smoke SMA, window2. At November9 2026 14:34 UTC, completed closes13 and19 average16. Change the same instance to window3, replay again: closes7,13,19 average13. Settings are saved through FastAPI/SQLite; the chart and displayed value are production calculations.
2. Switch to stored history and inspect14:34. Ask about chart uses the real capture/export. At each analyst/reviewer boundary, decode PNG filters/pixels, reject blank images, and check snapshot metadata, symbolAAPL, interval1m, selected candle and chart cutoff. Reviewer pixels must hash-match the analyst pixels. Known buy/up/sufficient answers must appear in Vue. Manual fill count stays0. Force a provider_error on a second manual capture and require that visible status; still0 fills.
3. Start automation from Vue after the14:34 baseline. Feed successive closes7,1,13,19 to produce a real upward SMA crossover at14:38; configured order size4. Fill at the next observed $100: $600/4shares. Send an exact duplicate observation and retry the job: still1 fill. Feed closes100,1,1; down crossover14:41 sells configured1 share at next $110: $710/3shares. The14:42 up crossover receives buy/reviewer-veto: still2 fills. Closes1,1 produce down crossover14:44; close the remaining3 at next $105. Require $1,025/0shares, realized$25/unrealized$0 in Vue and in an independent SQLite query. Intermediate completed candles mark open positions through production P&L logic. Stop from Vue, complete another candle, observe that updated candle in the UI, wait beyond the scheduler poll, and require unchanged job/order/fill counts.

Test controls change only the logical clock, input observations, configured order size and controlled provider mode. Production replay, SMA/indicator calculations, HTTP/WebSocket routes, PNG export, snapshot freezing, analyst/reviewer coordination, Python gates, simulator and ledger run unchanged. Test routes exist only in `backend.smoke_fixture:app`, require MARKET_SMOKE_TEST=1 and are never used by the normal launch. Every simulated source payload is labeled constructed. No test bypasses a strategy/account gate.

## Failure diagnostics and cleanup

Expected provider failure inside the normal scenario is a passing assertion. To exercise the runner's failure path deliberately:

```sh
SMOKE_INJECT_PROVIDER_FAILURE=1 python3 docs/smoke_test.py
```

This makes the first manual analysis fail where the test expects valid answers, so the command must return1, retain the screenshot/trace and terminate all owned processes. It does not change source. Remove the environment prefix for the normal test. Inspect result.json and logs, or open a retained trace with `frontend/node_modules/.bin/playwright show-trace <trace.zip>`.

SmokeTest reports only. AutoLoop is separate agent work: inspect failure, make a minimal authorized fix, rerun, stop on success or after five correction cycles. Do not silently loosen assertions to obtain a pass. The old structure-only check is retained as `python3 docs/structure_check.py`; it is not a UI smoke pass.

## CI and live evidence

`.github/workflows/smoke-test.yml` runs the same command twice on pushes, pull requests and manual dispatch. It uploads ignored run artifacts even on failure. No provider secrets are configured. The local folder is currently not a Git repository; the workflow has been prepared but no push/remote Actions execution is claimed. Review and commit/push through the student's authorized Git workflow when ready.

Offline passes do not verify live Yahoo availability, live image-model interpretation, or microphone/speaker audio. Those remain separate observations in verification.md and the live-dashboard, chart-analysis, decision-review and decision-voice notes. The offline suite never calls the voice provider or requests microphone access.
