# Project conventions

## Scope and ownership

- Work inside `/Users/mallorypierz/Documents/market_workstation`, the agreed project root. Inspect relevant files and Git status before editing; preserve existing work and the supplied starter collection/archive.
- Project: a local Assignment 4 market workstation, now preparing Part 4.2 (indicators, simulated trading and historical backtesting) on the existing Part 4.1 Yahoo dashboard and persistence foundation; the instructor reviews evidence.
- Current authorization (2026-11-17): perform the Part 4.2 readiness audit, run existing checks, create docs/part-4.2-checklist.md, and update scope/design/verification/handoff documentation. This audit does not authorize new feature implementation. The sequence in prompts/19-part-4.2-prompt-sequence.md is a plan; execute subsequent steps only when requested. Preserve all previously authorized features below. No installation, dependency-manifest change, commit or push is requested for this audit.
- Subsequent authorization (2026-11-17): execute the focused Part 4.2 SMA verification step using09a, independent reference calculations, causal/isolation tests and actual browser evidence. Only necessary SMA gaps may be fixed; historical backtest implementation remains a later request.
- Python owns calculations and backend logic; FastAPI transports requests/results through HTTP and WebSockets; Vue owns input and presentation; SQLite persists decoded observations and receipt/revision history. No deployment is required.
- Part 4.1 excludes indicators, trading, backtesting, AI features, and audio. The student explicitly authorized the two-SMA extension on 2026-11-15; the student subsequently authorized the shared indicator interface, named SQLite settings and rolling range extension. The student also explicitly authorized local long-only paper execution and account persistence; this is simulation only, with no real broker integration. The student also authorized weighted-average paper P&L history and completed-candle valuations. The student subsequently authorized frozen decision snapshots and proposal-only OpenAI Decisions calls, without executing orders. The student also authorized frozen chart PNG analysis with three named questions, without order execution. The student also authorized separate analyst/reviewer calls with a deterministic Python final gate, without execution. The student also authorized reviewed paper automation, fresh chart capture, Stop fencing and idempotent simulator execution; real brokerage remains excluded. The student also authorized read-only two-way voice discussion of a selected recorded decision via GPT-Live/WebRTC; voice must never submit orders or mutate the ledger. Only these requested additions are in scope. Later-part prompts in the supplied collection are references, not authorization to execute them. CSV practice is not live-streaming evidence.
- Show the changed files and a concise diff summary for student review before any commit. Do not initialize, commit, push, or delete Git repositories merely because a prompt file suggests it. The current setup task does not request Git changes.
- Save each major prompt under `prompts/` and its observed results in `docs/verification.md`. Inspect existing numbering first; preserve supplied files and reuse an existing prompt instead of duplicating it. The startup prompt is already preserved as `01-generic-project-startup.md`.
- Keep credentials out of code, prompts, logs, screenshots, and Git. Before introducing credentials, database files, or generated environments, add appropriate ignore rules. Do not expose secrets in diagnostic output.

## CHECK → TAKE ACTION → VERIFY

Use this procedure whenever a tool or package is needed:

1. **CHECK:** Inspect the OS, active Python interpreter, Node.js, package managers, dependency files, and lockfiles. Verify availability in the intended environment. Reuse the existing Python environment; do not create or recreate a virtual environment by default. Currently selected interpreter: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`. Recheck on resume.
2. **TAKE ACTION:** For each dependency missing and necessary for the current task, explain its purpose, compatible version (verified before proposing installation), exact command, installation target, and files it will change. Obtain student approval before installing software or creating/changing a dependency manifest or lockfile. Prior approval only covers its stated scope. Do not install future-task dependencies during documentation setup.
3. **VERIFY:** Run the smallest relevant version/import/build check in the intended environment. Record command, expected outcome, observed outcome, and any remaining checks in `docs/verification.md`. Report failures honestly; installed tools do not establish a working application.

## SmokeTest

SmokeTest is a repeatable check that runs without source edits. Current command, from the root:

```sh
python3 docs/smoke_test.py
```

This command now starts isolated FastAPI/Vue, opens real Chromium with pinned Playwright, exercises replay/SMA editing, chart capture and reviewed paper automation, compares Vue with SQLite, and exits nonzero on missing results. It uses deterministic offline boundaries and no provider credentials. It always cleans up owned browser/processes and retains evidence under ignored test-results/smoke/. Each run uses a fresh database/account. See [exact checks and approved setup](docs/smoke-test.md). SmokeTest never edits source or installs software. The old structure-only check is docs/structure_check.py; it is not a UI pass. GitHub Actions runs the same SmokeTest twice on push. Keep live Yahoo/image-model/voice evidence separate. Approval is still required for future installations.

## AutoLoop

On a failed check: inspect the failure, make the smallest in-scope correction, and rerun the relevant check. Record each failure, correction, and result. Stop on success, after five correction cycles, or when further permission is needed. Report remaining blockers; do not broaden scope or install packages to bypass approval.

## Data and evidence

- Preserve source and receipt timestamps, observation identity, revisions, and candle completion once implemented. Specify deterministic duplicate/out-of-order rules and verify cumulative-volume semantics before calculation.
- Distinguish socket connectivity from source freshness and market-session status. Label synthetic data and replay explicitly; neither proves live availability.
- Verify UI work in a running browser. Trace real source observations through storage, backend transport, and chart before claiming end-to-end live verification.
- Maintain README, design notes, verification results, and current handoff. Follow `handoffs/create-handoff.md` when ending or resuming a session.

## Chart analysis SmokeTest

`python3 -m backend.chart_smoke` starts isolated synthetic-data services on localhost5174/8010 with a controlled provider and no API key. Perform the documented browser operation in docs/chart-analysis.md, then run backend.chart_check to verify saved PNG bytes, provider input, answers and zero orders. Ctrl+C stops the services. This is a supervised UI SmokeTest, not an unattended browser pass; record whether the agent or student operated the UI and any browser-tool block. The original structure-only command remains available.

## Paper automation SmokeTest

Run `python3 -m backend.automation_smoke` and follow [the supervised browser steps](docs/paper-automation.md). Use only its disposable test account and controlled provider; stop automation and services afterward.


## Deterministic Part 4.2 strategy authorization

On 2026-11-17 the student authorized model-independent SMA crossover execution using existing paper/P&L code, isolated strategy accounts, Start/Stop fencing, receipt-boundary/idempotency tests and browser verification. Policy: one-share buy when flat/affordable on confirmed up; close on down; no pyramiding/shorting/borrowing. Preserve AI-reviewed automation. No real brokerage, new dependency installation, commit/push or historical backtest is authorized by this step. See docs/sma-strategy.md.


## Historical backtest authorization

On2026-11-17 the student authorized Part4.2 sequential historical backtesting using the verified crossover/paper accounting, frozen inputs/configuration, isolated accounts, causal tests, persisted results/metrics and a separately identified real historical evaluation. This includes a labeled bar-only adapter when the existing capture is insufficient. Preserve source records and original live/AI workflows. No real brokerage, dependency installation, commit/push or dedicated Vue backtest UI is requested in this step. See docs/backtesting.md.

## Backtest interface authorization and verification

The student subsequently authorized historical backtesting and its FastAPI/Vue interface (Prompt19 steps5–6). Implemented isolated frozen runs, dataset/range controls, Python metrics/indicators and saved-result inspection. Preserve prior authorizations and AI workflow. Run `python3 docs/backtest_ui_check.py` for focused real-browser invalid/empty/pending/outage/restart and SQLite checks; this is separate from the required resume SmokeTest. No installation, manifest change, commit or push authorized by these steps.

## Part4.2 CI extension

On November18,2026 the student authorized Prompt14/Prompt19 step7 offline correctness/browser coverage and push-workflow changes. SmokeTest now includes a second isolated constructed-data strategy/backtest scenario with direct SQLite assertions. CI runs Python correctness tests and a Vue build before the two fresh smoke invocations. Preserve separate real Yahoo evidence. No dependency installation/manifests/commit/push authorized; remote success must be observed for an actual final submitted SHA, never inferred from a local pass.

## Part4.2 submission preparation

Student authorized Prompt19 step8: preserve Part4.1 report/evidence; audit and draft root report.md for Part4.2; maintain disclosure/evidence/docs; verify startup/source export with existing dependencies; record an actual30–60second local demonstration. No Canvas submission, dependency installation or commit/push is authorized by this preparation alone. Use explicit pending SHA/video/remote-CI fields until verified. Present changed files/diff for review before requesting any needed publication authorization. Part4.1 report archive is docs/archive/part-4.1/report.md.

## Part4.2 publication authorization

The student explicitly authorized committing and pushing all Part4.2 changes and updating submission documentation on November18,2026. This authorizes the reviewed implementation/evidence commit, remote CI/access verification and follow-up report/documentation commits. It does not authorize Canvas submission, real brokerage or new local dependency installation. Earlier preparation-only restrictions are superseded for this publication task.
