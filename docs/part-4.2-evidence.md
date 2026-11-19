# Part4.2 curated evidence — November18,2026

This log distinguishes independently checked numbers, constructed fixtures, real historical data and remote checks still pending. New curated textual logs normalize personal local paths to `<PROJECT>`/`<USER_HOME>`; no credentials, environment values, private-account screens or production databases are included. Existing historical evidence remains unchanged. Tests run with isolated temporary accounts; copied evidence databases remain ignored under test-results, not in the submission.

## Observed evidence map

| Claim | Observed evidence | Boundary |
|---|---|---|
|Independent SMA formula and all prefixes|[reference expected/observed](evidence/sma-part42-reference.json), [methodology](sma.md), backend/test_sma.py|Authored integer fixtures, SQL oracle; no live-market claim|
|Forward strategy and receipt boundaries|[strategy result](evidence/strategy-result.json), [SQL smoke results](evidence/part42-smoke/part42-sqlite.json)|Constructed quotes;0model calls,isolated account|
|Weighted-average accounting and restart|[accounting results](evidence/accounting-part42/result.json), [P&L explanation](pnl.md)|Independent expected values, API/browser/direct SQLite|
|Real historical evaluation|[Yahoo daily source](evidence/aapl-2025-daily.json), [saved result](evidence/backtest-yahoo-daily.json)|37bars,4warm-up/33evaluation,10fills,999.64equity;price-only,not live evidence|
|Actual UI/outage/restart|[historical browser result](evidence/backtest-ui/result.json)|Saved history; real backend stopped/restarted;SQLite identical|
|Controlled CI path|[first](evidence/part42-smoke/run1-result.json), [second](evidence/part42-smoke/run2-result.json)|Local passes only; remote CI pending|
|Current startup/source export|[result](evidence/part42-submission/source-export-result.json), [init](evidence/part42-submission/source-export-init.log), [tests](evidence/part42-submission/source-export-python-tests.log), [build](evidence/part42-submission/source-export-build.log), [smoke](evidence/part42-submission/source-export-smoke.log)|Clean candidate source export, not final-SHA Git checkout; dependencies reused|
|Actual recorded demo|[video](evidence/part-4.2-demo.webm), [duration](evidence/part42-submission/duration.json), [script](part-4.2-video.md)|59seconds;local playback verified,public linkpending|
|Repository access|[unauthenticated access attempts](evidence/part42-submission/repository-access.json)|HTTP200for repository page only; new commit/docs/video not yetpublished|

## Actual failure → revised approach → result

Prompt: [Prompt19 step8](../prompts/19-part-4.2-prompt-sequence.md), continuing Prompt14's smoke procedure and AGENTS AutoLoop.

`CI=true python3 docs/smoke_test.py` at run20261118T192959-23996 failed after the legacy scenario passed. The new scenario raised `TypeError: Cannot read properties of undefined (reading 'account')` at the full-result assertion. [Failure result](evidence/part42-submission/resume-failure.json) and [actual Playwright error context/source excerpt](evidence/part42-submission/resume-failure-context.md) are retained. The original trace.zip/screenshot remains in ignored test-results/smoke/20261118T192959-23996/browser/.

Inspection showed `runBacktest()` in [frontend/tests/smoke.spec.js](../frontend/tests/smoke.spec.js) waited for a “completed” label and immediately read the saved-run select. The new option list could still be loading, so its value was empty and GET `/api/backtests/` returned the list rather than one result. Previous successful runs had not exposed this timing window.

Changed code arms `page.waitForResponse` for the POST before clicking, checks201, reads that response's run_id, then waits until the select has **that** value before fetching the saved result. Decision/accounting code and expected numerical assertions are unchanged. Decision: keep the strict assertions and synchronize to the operation being tested; do not add arbitrary sleeps or hide failures with retries.

Rerun `CI=true python3 docs/smoke_test.py`:PASS run20261118T193234-24191,2scenarios39.9s. [Corrected result](evidence/part42-submission/resume-corrected.json). A second run in the clean candidate export also passed, run20261118T193457-24532. Both report cleanup. Earlier local passes remain historical evidence, not a reason to omit this real failure.

## Startup and reproducibility

`python3 docs/part42_checkout_check.py` copied277nonignored candidate files into a fresh temporary directory, without `.git`, runtime databases, environments or node_modules. It linked the already installed frontend dependencies and reused framework Python3.12.5/Node24.20.0/installed Chromium. No software was installed. Thus this tests a **clean source export**, not a clean dependency installation or a checkout of an uncreated submitted SHA.

From that export it ran:

1. `python3 -m backend.recorder init`:PASS; fresh observations/deliveries/revisions tables,0deliveries.
2. `python3 -m uvicorn backend.main:app --host 127.0.0.1 --port <free-port>` with feed disabled and temporary DB paths:health/startup PASS. POST real daily backtest produced999.64equity; direct SQLite saved result equaled HTTP response.
3. `python3 -m unittest discover -s backend -p 'test_*.py'`:110PASS in7.688s.
4. `npm --prefix frontend run build`:PASS,36modules.
5. `CI=true python3 docs/smoke_test.py`:both actual Chromium scenarios and direct SQL assertions PASS, with fresh temporary accounts.

The result records source-file hashes, exact command exits and service cleanup. Source export was made before the final documentation/media curation; implementation and corrected smoke test were included. A final submitted-commit checkout and dependency restoration remain separate post-publication checks. Existing dependencies are disclosed, not represented as freshly installed.

## Video, access and preservation

`python3 docs/part42_video.py` recorded actual normal Vue/FastAPI using saved constructed and Yahoo historical runs with fixed2/3parameters. `DEMO_OUT="$PWD/test-results/part42-video" node frontend/tests/part42-video-inspect.mjs` measured59.00seconds from the encoded video and decoded sample frames. The agent visually inspected SMA/crossing, linked fill,account/performance, historical curve/trades and assumption/limitation segments. Captions are narration; result values were not edited. No audio or model calls. Owned services stopped and temporary accounts removed.

A default urllib repository request failed certificate verification. Reusing installed certifi's CA bundle with TLS verification still enabled returned unauthenticated HTTP200. This is a repository-page check only. No video has been published yet; no instructor video access or remote Actions conclusion is claimed. No commit/push/Canvas submission occurred.

The [Part4.1 report](archive/part-4.1/report.md) and disclosure were copied verbatim before editing. [Preservation manifest](archive/part-4.1/preservation.json) identifies retained original evidence. The112.08second previous video remains historical material, not the Part4.2 link. Root report.md is now a clearly pending Part4.2 draft. All final supporting links must be checked at the eventual submitted implementation/evidence SHA before Canvas upload.

Final video revision: first capture56.00s; clearer historical-trade centering caused revised encoded length60.92s, failing the ≤60second check. Installed Playwright FFmpeg stream-copied only the first59seconds (`-t 59 -c copy`); final Chromium measurement59.00s passed. Final frame42shows the historical filled buy row; frame53retains the limitation caption. The final file/hash/frames replaced the earlier draft; no performance values changed.
