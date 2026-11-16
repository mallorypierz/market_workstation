# End and resume a session

1. **At handoff:** Write `handoffs/current.md` with the agreed project root and purpose, files created/changed, exact checks and observed results (including failures), environment/dependency status, outstanding questions or approvals, and the next in-scope task. Distinguish implemented behavior from plans; omit secrets.
2. **On resume:** Read `AGENTS.md` and `handoffs/current.md`, verify the current path, contents and Git status, then run `python3 docs/smoke_test.py` and relevant environment checks. Compare actual state with the handoff before editing; preserve concurrent work and report discrepancies.
