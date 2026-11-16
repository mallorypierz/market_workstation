# Reviewed paper automation

This later-part extension is local simulation only. `prompts/12-apply-reviewed-paper-decision.md` preserves the request. No new dependency or manifest changes were needed.

## Execution path

Vue's `PaperAutomation.vue` observes completed candles in the existing WebSocket view. Start records the most recent completed candle as a baseline; it does not trade old history. For each later completed candle, Python reserves a unique account/strategy/symbol/interval/candle job and freezes a snapshot. Vue reuses `captureChart` to render exactly those saved candles/volume/indicators and submit a fresh PNG. Python reuses `decision_review.run`: one bounded call per role, the same snapshot and PNG, and independent deterministic checks.

The saved decision is linked to the job. Only a complete matching snapshot, valid image answers, reviewer acceptance and passing Python account/strategy/evidence rules can submit an order. Missing images are saved as failed analysis and skipped. An ordinary `/api/decisions` call never submits an order. Buy/sell use frozen configured order size; close requests the entire current position; hold/wait produce no order.

`paper.execute` uses a stable request ID derived from the job. Accepted orders remain pending for the next eligible first-seen observation after submission. Immediately before fill, the simulator checks current cash/shares; automation checks the control generation, age, snapshot identity, prior handling, review and Python validation again. The fill, cash, position, P&L, decision linkage and job result share one SQLite transaction. Retry returns the existing job, order and fill.

Default expiry is 120 seconds after the candle's interval ends, configurable by `MARKET_DECISION_MAX_AGE_SECONDS` (1–3600). Both processing time and receipt time must remain within this bound. With no new quote, a pending order remains visible until Stop/restart or a quote triggers expiry rejection; it cannot fill after expiry. Existing price rules remain rounded cents, zero fees, observed quote rather than guaranteed exchange execution.

Stop atomically disables the control, increments its generation, cancels unfilled automated orders and skips unfinished jobs. A model reply that returns later may be retained for inspection but cannot execute. Already committed fills remain. Backend startup performs the same fence and requires a new Start. Unique claims survive restart and equivalent UTC timestamp spellings are normalized. A later revision does not run a second analysis for an already claimed candle.

Automation needs the dashboard open to schedule captures. It supports AAPL and the backend's intervals, with SMA settings included in the strategy identity. Switching scope/settings or entering Replay stops automation. Replay paper automation is not implemented. Snapshot history still uses only observations/revisions received by the decision cutoff. Old/unavailable/incomplete captures skip execution rather than borrowing newer facts.

Constructed snapshots may execute only in account `automation-test`, when `MARKET_AUTOMATION_TEST=1` and the configured database is inside the OS temporary directory or `/private/tmp`. Start routes to that separate $1,000 account. Normal labeled test snapshots remain ineligible. The normal paper account is untouched by this fixture.

## Repeatable supervised SmokeTest

1. Run `python3 -m backend.automation_smoke` from the root. It prints a newly allocated SQLite path and starts localhost5174/8010. Yahoo is off; the provider is controlled; the child environment omits the API key. The fixture clock starts at 2026-11-09 14:34:55 UTC, with prices 13, 10, 7, 13, 19 in successive minutes.
2. Open http://127.0.0.1:5174/ in a browser. Leave AAPL/1m and windows 2/3. Click **Start paper automation**. Expect the disposable account at $1,000, zero shares/fills.
3. Run `curl -s -X POST http://127.0.0.1:8010/api/fixture/advance`. The fixture clock reaches 14:35:01. Expect automatic PNG capture for the 14:34 candle, SMA 16/13/up, analyst buy, reviewer accept, Python pass, one pending order.
4. Run `curl -s -X POST http://127.0.0.1:8010/api/fixture/price`. This supplies the constructed next price $20 at 14:35:10. Expect one fill, $980, one share and zero P&L, with one decision ID linking the trace. Open Frozen PNG to inspect the exact saved chart.
5. Retry `POST /api/automation/jobs/{job_id}/apply` using the ID in SQLite. Expect the same order/fill and unchanged balance. Compare `automation_jobs`, `paper_accounts`, `paper_positions`, `paper_fills`, `paper_pnl` and `decision_images`; the saved PNG SHA-256 must match `chart_provider_calls.png_sha256`.
6. Click **Stop paper automation**; expect Stopped. Press Ctrl+C in the fixture terminal to stop both services. Test-only clock/price routes exist only in `backend.automation_smoke:app`, not the normal app launch.

Run `python3 -m unittest backend.test_automation -v` for duplicate claims/application, persistent restart deduplication, reviewer veto, Stop during a provider call and while an order is pending, expiry, cash recheck on price jump, missing capture and transactional rollback. Unit PNGs are constructed test images; the browser check uses an actual Lightweight Charts export. These are controlled-provider checks, not live market/model evidence.
