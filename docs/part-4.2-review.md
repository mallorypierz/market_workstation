# Part4.2 pre-publication review

The review below was presented before authorization. The student then authorized publication: implementation/evidence `8565d239f94a356f91cbd47054e416e8bc465345` is pushed to main; public access and [remote CI](https://github.com/mallorypierz/market_workstation/actions/runs/44444599750) passed. The path/diff files below preserve the pre-publication review rather than pretending to be the latest Git status.

## Candidate changes

- **Report and preservation:** root report.md now describes Part4.2 with pending submitted-SHA/video/remote-CI fields. docs/archive/part-4.1 preserves report/disclosure verbatim plus original-evidence hashes. The outdated checklist is replaced by a current evidence map; its original audit is archived.
- **Previously authorized implementation:** backend/strategy.py and backend/backtest.py add independent crossover execution and isolated historical runs; backend/main.py/paper.py integrate endpoints/shared accounting; Vue SmaStrategy/BacktestPanel/BacktestCharts and App/CandleChart integration expose controls/results. Weighted-average accounting and AI-reviewed workflow are retained.
- **Correctness/evidence:** independent SMA/accounting references, focused tests/browser runners and the new direct SQLite smoke verifier. Workflow adds correctness discovery/build before both smoke commands. This preparation fixes only the observed saved-selector synchronization race in frontend/tests/smoke.spec.js; production calculations and parameters are unchanged.
- **Demonstration/reproducibility:** docs/part42_video.py, frontend/tests/part42-video*.mjs record/inspect an actual59second app video; docs/part42_checkout_check.py verifies a clean source export with reused dependencies. Video is docs/evidence/part-4.2-demo.webm (about9.6MB), not the old112second file.
- **Documentation:** README, AGENTS, AI-USE, design/schema/verification/handoff, calculation/accounting/backtest guides and curated evidence. Existing prompts reused. Runtime DBs, environments, credentials and test-results remain ignored.

[All changed/untracked paths](evidence/part42-submission/review-status.txt) · [tracked diff summary](evidence/part42-submission/review-tracked-stat.txt) · [report/test/workflow diff](evidence/part42-submission/review-report-test-workflow.diff). The tracked diff summary excludes new untracked files; the path list includes them. The linked implementation files themselves are available for review in this working tree.

## Reviewed publication plan (now authorized and executed)

1. Commit the reviewed Part4.2 implementation, tests, evidence/video and documentation to the existing repository; record the real implementation/evidence SHA.
2. Push the authorized changes. Observe the workflow for that exact SHA, verify unauthenticated access to all report-linked documents and complete video playback/download.
3. Replace report.md pending fields with the verified implementation/evidence SHA, one public video URL and actual CI run/conclusion. Pin all supporting links to that version. A subsequent documentation-only commit can contain the finalized report without pretending it can name its own hash.
4. The student reviews and uploads **only report.md** to Canvas. No automatic Canvas submission.

If remote checks fail, record the actual failure and fix within authorized scope; do not label the report ready based solely on local tests. The final implementation-SHA clean checkout has now passed, with reused dependencies. The current candidate source export passed startup,110tests,build and both browser scenarios with existing dependencies.
