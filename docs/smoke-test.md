# Offline SmokeTest

Published implementation/evidence [8565d23](https://github.com/mallorypierz/market_workstation/commit/8565d239f94a356f91cbd47054e416e8bc465345); [remote CI](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) **success**; [59-second video](https://raw.githubusercontent.com/mallorypierz/market_workstation/8565d239f94a356f91cbd47054e416e8bc465345/docs/evidence/part-4.2-demo.webm) verified by unauthenticated full download and matching SHA256. The exact committed checkout passed tests/build/browser checks with reused local dependencies. Student review and Canvas upload remain the student’s actions.

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

`.github/workflows/smoke-test.yml` runs the same command twice on pushes, pull requests and manual dispatch. It uploads ignored run artifacts even on failure. No provider secrets are configured. The repository is configured at https://github.com/mallorypierz/market_workstation. Part4.2 commit `8565d239f94a356f91cbd47054e416e8bc465345` is published and [its observed workflow](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) completed successfully. Both smoke invocations, correctness tests and the build passed. This remote result is separate from local evidence.

Offline passes do not verify live Yahoo availability, live image-model interpretation, or microphone/speaker audio. Those remain separate observations in verification.md and the live-dashboard, chart-analysis, decision-review and decision-voice notes. The offline suite never calls the voice provider or requests microphone access.

## Part4.2 deterministic coverage

The same Playwright file now has a second scenario. The opt-in fixture switches to a separately seeded disposable database after the original scenario; real application routes/calculations remain in use. The dataset picker and frozen provenance explicitly say constructed, not Yahoo evidence. A temporary `MARKET_BACKTEST_DIR` prevents reading or writing the student's saved backtests. No historical dataset is selected; no model calls occur in this scenario.

The browser starts the strategy before receipt1. Completed closes13,10,7,13 establish the expected warm-up gaps,8.5/10and10/10tie. Receipt5 contains unfinished19: no order. Receipt6 establishes completion:16/13up, one pending buy, no fill. Receipt7 supplies later100:900cash/1share. Completed7and1 produce13/13tie then4/9down. Receipt10 supplies later110:1010cash/0shares/10realized/0unrealized. Stop is clicked; direct SQL requires disabled state and an untouched1000cash live account.

Before any later price exists, Vue runs a prefix ending just after14:35, leaving a pending buy and no fills. After later receipts arrive, a new run of the same prefix must retain identical decisions/equity and zero fills. The full run displays1010equity,1%return,9.9%drawdown (initial1000, minimum901), both crossing directions and saved-result reload without extra fills. Invalid equal windows produce a visible error and a direct API422. Python correctness tests separately perturb future observations/revisions and cover duplicate/out-of-order/isolation behavior.

`docs/smoke_part42.py` independently queries SQLite after Chromium: all seven SMA pairs/signals, receipt boundaries, fill quantities/prices, cash/positions/exact P&L, zero model calls, three saved result JSON records and known performance identities. The browser response is compared with persisted results, not used as the expected numerical oracle. A post-browser SQL assertion failure returns exit1. Evidence includes `part42-browser.json`, `part42-sqlite.json`, `part42-backtest.png`, the disposable `part42.sqlite3` copy and `backtests/` ledger copies. Working accounts/databases are removed after owned services stop; ignored evidence copies intentionally remain.

Push/PR/manual CI now runs `python3 -m unittest discover -s backend -p 'test_*.py' -v`, `npm --prefix frontend run build`, then the original two invocations of `python3 docs/smoke_test.py` (each invocation runs both browser scenarios with fresh accounts). The existing dependency-install and artifact-upload steps remain. The separate real-Yahoo historical browser check remains `python3 docs/backtest_ui_check.py`; it is historical evidence, not part of controlled smoke acceptance.
