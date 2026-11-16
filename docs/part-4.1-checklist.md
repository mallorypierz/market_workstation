# Part 4.1 readiness checklist — November 15, 2026

**Not yet submission-ready.** This audit uses the supplied Part4.1 text and pasted overview, including submission/evidence requirements. Later-part features do not fill Part4.1 gaps.

| Requirement | Implementation | Verification / evidence | Status |
|---|---|---|---|
| Yahoo live prices → candles | live.py commits receiver messages; candles/timeframes; FastAPI stream; Vue chart | live-yahoo-candle-trace.json and live-yahoo-trace.png; retained record197 checked again | Verified historical live capture |
| Corresponding live volume | aligned volume histogram; null for unknown live values | Synthetic850-share bar verified; live volume semantics unverified | **Open feature/evidence gap** |
| WebSocket and visible source/age/status | independent upstream/browser/freshness/session state; authoritative snapshots | live trace and upstream-disconnected.png; live tests | Implemented; retained live evidence |
| SQLite identity/source/receipt/raw payload | observations + deliveries + explicit revisions |197 unique/199 receipts; recorder tests | Verified |
| Completion and late revisions | derived interval/coverage metadata; recompute using receipt cutoff | candle/timeframe/replay tests, schema/rules | Verified in constructed tests |
| Duplicates/revisions/out-of-order | exact-repeat identity; retain ambiguous changes; explicit correction links |32 focused tests pass; real capture has no evidenced revisions | Verified with stated limits |
| Retrieval/replay with Yahoo off | read-only recorded selection in arrival order | replay-check.json: twice, close356.24 and stable DB hash | Verified historical browser run |
| Unavailable feed | failure/status UI and bounded reconnect; no stale data presented as fresh | disconnect screenshot and transport tests | Manual upstream disconnect verified; tests cover errors |
| README/AGENTS/data flow/schema/startup/init | Existing maintained documents | build and relevant tests pass | Present; clean checkout still pending |
| Report | report.md draft | honest feature/evidence summary | **Needs final links and commit** |
| GitHub URL + submitted commit | Public mallorypierz/market_workstation; code snapshot370948b7366ba13d0023fe222f1c631dbc6d2e37 | Pushed main preserving old history; report links pinned | Published |
| One30–60second video with access | storyboard below | No video link supplied | **Missing** |
| AI-use disclosure and curated evidence | AI-USE.md, part-4.1-evidence.md | grounded in observed session records | Student review of model/editor history needed |
| Instructor access / clean checkout | Repository public; video missing | Clean tracked checkout tests/build pass using existing installed dependencies; full browser SmokeTest passed | Fresh-runner CI passed; video access still pending |

## Before finalizing

1. Resolve live-volume semantics and capture corresponding bars, or explicitly submit the limitation without claiming full compliance. Never substitute CSV/test volume for Yahoo volume.
2. Review AI-USE.md and the report for personal accuracy; add any other tools/models actually used.
3. Review the file set, initialize/connect the intended repository if authorized, commit/push the reviewed version, and record its actual SHA. Keep runtime DBs/keys/test caches ignored. Preserve the supplied starter collection locally.
4. Local clean tracked checkout tests/build/browser passed using existing installed dependencies. Fresh-runner CI passed both SmokeTest runs; confirm instructor access to the eventual video.
5. Provide one30–60second accessible video; confirm duration/access. Update report.md with its link.
6. Replace draft-relative report links with full repository URLs pinned to the submitted commit so links work when report.md is viewed from Canvas. Remove draft warnings only after outstanding items are resolved or explicitly disclosed. Upload only report.md.

## Suggested 50-second video

- 0–15s: Yahoo/AAPL chart updating during a live capture; show source/time/age/feed status and candle/volume state honestly.
- 15–25s: identify the matching saved observation and source/receipt times; explain commit-before-broadcast.
- 25–35s: disconnect Yahoo while the browser connection stays up; show the changed status.
- 35–45s: replay a recorded selection with Replay clearly visible; inspect a matching candle.
- 45–50s: name one design/verification decision (duplicates reuse identity; unknown volume is not zero).

If recorded when the market is closed, clearly distinguish any earlier live recording from current replay. A screenshot or replay alone is not new live-streaming evidence. Do not expose keys or private windows in the video.
