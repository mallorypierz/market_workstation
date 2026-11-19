# Part 4.2 — Indicators, simulated trading, and backtesting

Prepared November 17, 2026 from the student-supplied Assignment 4 overview and its Section 6 submission requirements. [Assignment overview](https://psu.instructure.com/courses/2484533/pages/assignment-4-overview-live-market-workstation) · [Part 4.2 submission](https://psu.instructure.com/courses/2484533/assignments/18507004). The supplied overview contains the Part 4.2 requirements even though the request also quotes Part 4.1. No due date is inferred.

Use these prompts **one at a time, in order**. This document is a plan, not evidence of completed Part 4.2 work. Creating it does not execute its implementation prompts or authorize installations, commits, pushes, or submission. Existing Part 4.1 evidence and later-part features must be preserved.

## Existing work to reuse

- [09a — Two SMAs and crossovers](09a-calculate-moving-averages.md): implemented calculation and reference fixture; audit and extend verification rather than rebuild.
- [09b — Named indicators](09b-create-chart-indicators.md): existing optional indicator interface; adding more indicators is not required.
- [09c — Paper trading](09c-build-paper-trading.md) and [09d — P&L](09d-record-profit-and-loss.md): existing orders, fills, account persistence, and weighted-average accounting.
- [14 — SmokeTest](14-automate-workstation-smoke-test.md): existing browser runner and push workflow; extend their coverage.
- Current design: [SMA](../docs/sma.md), [paper execution](../docs/paper-account.md), [P&L](../docs/pnl.md), [pipeline](../docs/design-pipeline.md), [SQLite](../docs/sqlite-schema.md).

The inspected project has AI-reviewed paper automation, but this does not by itself demonstrate a deterministic SMA backtest. No dedicated backtest implementation was found in the inspected backend files. Confirm the current state in Prompt 1.

## Rules shared by every prompt

Read AGENTS.md and handoffs/current.md; work in the agreed root, inspect Git status, and preserve existing changes and the starter archive. Follow CHECK → TAKE ACTION → VERIFY and AutoLoop. Reuse the current Python environment. Obtain student approval before installing dependencies or modifying manifests/lockfiles. Python owns calculations, FastAPI transport, Vue presentation, and SQLite persistence. Keep all trading simulated, local, and long-only; no real brokerage, deployment, or new AI/audio work is needed for Part 4.2. Never expose credentials.

For each executed prompt, record files changed, exact checks, expected and observed results, failures/corrections, evidence paths, and limitations in docs/verification.md; update the current handoff. Distinguish plans from implemented behavior and synthetic tests from real historical or live data. Show a concise diff summary. Do not commit or push without a current explicit instruction to do so.

## 1. Audit Part 4.2 readiness and agree on the implementation boundary

```text
We are preparing Assignment 4, Part 4.2. Follow the shared rules in
prompts/19-part-4.2-prompt-sequence.md. Inspect the existing code, tests,
documentation, Git status, runtime versions, and dependency manifests.
Run the required resume SmokeTest and report its actual result.

Create docs/part-4.2-checklist.md mapping each requirement to existing files,
evidence, gaps, and a concrete acceptance check: two SMAs/crossovers;
completed versus unfinished candles; reference and batch/incremental
verification; crossover-driven simulation; orders/fills/cash/positions/P&L;
historical backtesting without future information; understandable results;
browser checks; GitHub Actions on push; report/repository/commit/video.

Reuse prompts 09a–09d and 14. Inspect whether the current automation requires
AI calls and whether a deterministic crossover strategy can run independently.
Document the smallest remaining implementation plan and proposed execution
assumptions. Update AGENTS.md and README scope to reflect this Part 4.2 work
without erasing prior authorizations or claiming planned features exist.
Do not implement new features in this audit step.
```

## 2. Verify the existing SMAs and crossover calculation

```text
Use existing prompt 09a and backend/sma.py as the baseline. Inspect and fix
only gaps needed for Part 4.2. Keep two configurable positive integer windows,
short < long, visible lines and crossover markers, warm-up gaps, and exact
comparison before display rounding. Explain ties and first-comparable values.

Verify against an independent trusted reference: retain the hand-worked
13,10,7,13,19,7,1 example with windows 2 and 3, and compare a longer fixed
dataset against an independent reference calculation. Identify its provenance,
formula, tolerance and expected outputs. Do not install a reference library
without approval or compare the function only to itself.

Compare all batch values and signals to one-candle-at-a-time results at each
available-data prefix, including warm-up. Clarify whether incremental means
prefix recomputation or a stateful rolling implementation. Test equality,
revisions, duplicates, late arrivals, missing intervals and symbol/timeframe
isolation. Future corrections must not leak into earlier prefixes. Unfinished
candles must not produce confirmed trade signals; if provisional values are
shown, label them explicitly. Inspect both lines and markers in a running
browser and retain reference results and screenshots. Update docs/sma.md.
```

## 3. Connect the SMA strategy to the existing paper simulator

```text
Reuse the existing paper execution and P&L code from prompts 09c and 09d.
Provide a deterministic Part 4.2 SMA crossover strategy that needs no model
API or provider credentials. Preserve the existing AI-reviewed workflow.

Use a simple documented policy: on a confirmed upward crossover, buy one
share when flat and affordable; on a downward crossover, close the position;
otherwise do nothing and show why. No shorting, borrowing or pyramiding.
Keep configuration and run/account identity explicit. Use completed candles
only. A signal queues an order; fill only at a later eligible observation,
never retroactively at the price that created the signal. Reuse the simulator's
documented receipt-boundary and execution rules; expose their limitations.

Make signal -> order or skipped reason -> fill -> account state traceable.
Use stable event/request identities so repeated polling, duplicate receipts,
retry and restart cannot execute a signal twice. Explain how a late revision
can change displayed history without rewriting an already executed fill.
Use disposable accounts in tests and keep replay/strategy accounts isolated
from existing live and AI accounts. Provide start/stop behavior for an ongoing
run and prevent further strategy submissions after Stop.

Test upward/downward signals, no crossover, insufficient cash, warm-up,
unfinished candles, retry/restart and no later fill price. Inspect the actual
Vue controls, pending/filled/rejected states and linked trade history in a
running browser. Update execution assumptions and SQLite/data-flow notes.
```

## 4. Reconcile simulated accounting against known examples

```text
Reuse prompt 09d rather than replacing weighted-average accounting. In an
isolated $1,000 account verify: buy 4 at $100 -> $600 cash/4 shares;
mark at $110 -> $40 unrealized; sell 1 at $110 -> $710 cash/3 shares,
$10 realized/$30 unrealized; mark at $95 -> $10 realized/-$15 unrealized;
close 3 at $105 -> $1,025 cash/0 shares/$25 realized/$0 unrealized.

Add a multiple-buy example to verify weighted-average cost, rounding and
partial-sale behavior independently. Check equity = cash + marked position
value and total P&L = realized + unrealized under the stated zero-fee rules.
Document fees, slippage, full-fill, price rounding and valuation assumptions.
If no valid valuation is available, display unavailable, not a fabricated zero.

Compare API and browser values with direct SQLite queries before and after
restart. Verify atomic order/fill/account updates, nonnegative cash/positions,
idempotent events, rejected oversells and unchanged market-source records.
Save expected-versus-observed results and explain any existing discrepancy.
```

## 5. Build a reproducible historical backtest in Python

```text
Implement Part 4.2 backtesting using the verified crossover policy and shared
paper accounting. Replay alone is insufficient: evaluate strategy decisions,
orders/fills and resulting account performance. Prefer sequential processing
of recorded Yahoo observations in receipt order using the existing known-at
filtering. Freeze input selection and parameters at run creation.

Persist each run's ID, instrument/timeframe, date range, data provenance,
dataset hash or immutable selection/cutoff, windows, initial cash, sizing,
execution assumptions, version identifier when available, status and results.
Use an isolated account/run and preserve input observations. Define warm-up
data versus the evaluation period. No pre-period trade may enter performance.

At each step, reveal only data and revisions available then; form completed
candles, calculate signals, and submit orders that can fill only after the
decision boundary. Do not precompute signals from a finally revised history.
Retain an audit trace from each decision through fill and valuation. End with
open positions marked at the last usable known completed-candle price; show
pending orders and avoid an invented liquidation price.

If existing captures are too short for meaningful crossings, support a clearly
labeled historical dataset with documented source, retrieval time, timezone,
session, adjustment/split/dividend policy and missing-data rules. For bar-only
data, explicitly define close-time availability and next-bar execution, and
explain that original receipt/revision history is unavailable. Do not relabel
the practice CSV as Yahoo evidence. Use synthetic fixtures for correctness
tests and a separately identified real historical run for evaluation. Do not
silently download packages or use the production account.

Return and persist trades, cash, positions, realized/unrealized P&L, equity
curve, total return and maximum drawdown with documented definitions. Include
initial equity in the curve and disclose sample size and open positions.
Test a hand-verifiable run, no trades, inadequate warm-up, duplicates, late
corrections, no next fill, repeatability and account isolation. Prove causality
by changing future observations/revisions and verifying earlier decisions
and fills remain identical. Document remaining data/execution limitations.
```

## 6. Add the backtest controls and results to Vue

```text
Expose the Python backtest through validated FastAPI endpoints and Vue controls
for available dataset/range, symbol/timeframe, two SMA windows and starting
cash. Show simulation mode, provenance, execution assumptions and run status.
Keep calculations in Python and validation on both sides. Reject invalid or
empty selections with useful errors; never silently substitute synthetic data.

Display the two SMA lines and crossover markers alongside backtest trades,
linked decisions/orders/fills, cash, position, realized/unrealized P&L,
equity curve, return and drawdown. Make pending or skipped actions and their
reasons inspectable. Reload a saved result after restart without rerunning it
or duplicating fills. Keep backtest results separate from live account state.

Use real browser interaction to run a known dataset, inspect an upward and
downward crossing, reconcile results with SQLite, refresh/restart, and check
invalid parameters, empty data and backend failure. Save screenshots and a
traceable result artifact. Update startup and schema documentation.
```

## 7. Extend automated checks and verify GitHub Actions coverage

```text
Reuse prompt 14, docs/smoke_test.py, the existing Playwright runner and
.github/workflows/smoke-test.yml. Add deterministic offline coverage for the
Part 4.2 path: completed SMA crossover -> strategy order -> later fill ->
account/P&L -> saved backtest and performance display. Assert known numbers
against SQLite, not merely that elements exist. Include a no-look-ahead check,
unfinished-candle check and an error path. Keep real historical/live evidence
separate from controlled browser fixtures. Clean up owned services/accounts.

Run focused Python tests, relevant frontend checks/build and the full browser
SmokeTest. Ensure the push workflow actually runs the relevant correctness
tests as well as the browser smoke checks; preserve the existing two-run smoke
coverage. Do not install dependencies or modify manifests without approval.

Record exact commands/results and evidence. Inspect the remote workflow for
the final submitted commit when it exists; link the observed run/conclusion.
Local success is not proof of remote CI success. Do not push solely to trigger
CI unless the student has explicitly authorized that action.
```

## 8. Prepare the Part 4.2 report and 30–60 second demonstration

```text
Audit docs/part-4.2-checklist.md against observed evidence. Preserve Part 4.1
report/evidence before preparing the root report.md for Part 4.2. Summarize
what works, design decisions, reference/batch/incremental verification,
known accounting examples, browser/CI results and remaining limitations.
Explain the historical run's trades/performance, look-ahead protections,
survivorship bias, overfitting, sample limitations and why historical profit
does not establish future performance. Do not tune parameters to manufacture
a positive return. Link relevant docs, tests and evidence.

Maintain README, AGENTS, design/schema notes, handoff, AI-USE.md and a curated,
redacted evidence log. Include an actual failure or revised approach with its
prompt, changed code, observed test result and resulting decision. Do not
invent a failure or claim an unperformed check. Verify startup/database
initialization and a clean checkout when feasible; disclose reused dependencies.

Prepare a 30–60 second video script: roughly 0–15s show two SMAs and a
crossover; 15–30s trace a simulated order/fill and account/P&L; 30–50s show
historical backtest trades, equity/performance and assumptions; 50–60s identify
one correctness check or limitation. Record the actual running application
if tools allow, otherwise leave precise recording instructions for the student.
Measure the final duration and confirm the instructor can access the link.
The prior 112-second Part 4.1 video is not a compliant Part 4.2 demonstration.

Include the real GitHub repository URL, exact submitted implementation commit
and one accessible video link in report.md. Use explicit pending fields until
these are verified; never fabricate a SHA or URL. Show changed files/diff for
review before any authorized commit; request commit/push authorization only
if needed after preparation. Ensure linked docs/evidence are accessible at the
submitted version. Upload only report.md to the Part 4.2 Canvas submission;
source and ZIPs stay out of Canvas. Do not submit on the student's behalf.
```

## Requirement coverage

| Assignment requirement | Prompts |
| --- | --- |
| Two different SMAs, crossover, unfinished candles | 2, 3, 6 |
| Trusted reference and batch/incremental agreement | 2, 7 |
| SMA strategy applied to simulated account | 3, 5 |
| Orders, fills, cash, positions, realized/unrealized P&L | 3, 4, 5, 6 |
| Historical backtest using only available information | 5, 7 |
| Trades/performance and limits of interpretation | 5, 6, 8 |
| Browser testing and automated checks on pushes | 6, 7 |
| Current docs, report, repository/commit, 30–60s video | 1, 8 |
