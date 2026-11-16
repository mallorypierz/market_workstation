# Analyst and reviewer decisions

POST `/api/decisions` now runs the analyst and reviewer separately under the existing decision ID. No agent is granted order execution or database-write tools. The endpoint remains a local paper-account analysis endpoint. Reused prompt: [11-add-agent-review.md](../prompts/11-add-agent-review.md).

## Request trace and stored inspection

```text
POST /api/decisions {snapshot_id, optional chart image/binding}
  -> backend.main.request_decision
  -> decision_review.run
  -> existing decisions.decide / chart_analysis.analyze
  -> one analyst call using existing decisions.openai_request
  -> persist analyst output, review_pending, order_eligible=false
  -> one reviewer call using that same client
  -> Python account/strategy/evidence checks
  -> update the same decisions.result_json
GET /api/decisions/{decision_id} -> both roles and final check
```

The snapshot is created independently by the existing snapshot route. Neither model can request a new snapshot. Both roles receive exactly the saved snapshot and digest, including symbol, completed candles, SMA windows/values, crossover, historical simulated cash and shares. For chart questions, the reviewer also receives the exact same image data URL and the analyst's actual named answers. No chart is redrawn between calls.

`roles.analyst` and `roles.reviewer` expose model, provider, snapshot ID/digest, image hash when applicable, call_count, timeout_seconds, timestamps, exact question instructions, categorical output and role status. A returned provider model name is retained when available. The analyst's original validation is retained separately. `final_check` records account/strategy/chart checks, observed cash/price/size/shares/crossover, reviewer acceptance, snapshot eligibility and final eligibility. Existing proposal, answers, image, explanation, validation and decision_id response fields remain available.

Students can inspect the complete result through GET using its decision ID. The existing chart panel still displays the analyst's three answers and the final status/explanation; this task does not add a separate Vue role-trace panel. Saved historical results without roles/final_check remain historical evidence, not proof of completed review.

## Independent instructions and final policy

The analyst proposes one action. The reviewer receives that actual proposal, its named chart answers where present, the immutable snapshot and Python's supporting values. The reviewer is told to evaluate rather than replace the proposal, and chooses one named `review_verdict` category:

- accept
- reject_insufficient_cash
- reject_insufficient_position
- reject_unsupported_signal
- reject_unreadable_evidence
- reject_invalid_proposal

Both roles currently use gpt-6-luna. This follows the official [Decisions guide](https://developers.openai.com/api/docs/guides/decisions): category-only answers need no generated rationale. Python supplies the explanation from recorded values instead of attributing invented reasoning to the model.

The explicit `sma-cross-v1` rules are shared in instructions and independently enforced in Python:

| Action | Account rule | Signal rule |
| --- | --- | --- |
| buy | Configured size × cent-rounded close must fit simulated cash | Upward crossover |
| sell | Configured size must not exceed held shares | Downward crossover |
| close | Open position required; proposed size is the whole holding | Downward crossover |
| hold | Open position required | No downward crossover |
| wait | Flat position required | Allowed regardless of signal; no forced buy |

Chart answers must also report sufficient readable evidence and agree with Python's crossover. Reviewer acceptance cannot override any check. A model rejection blocks the proposal even when Python's account/strategy checks pass; contradictory rejection reasons are shown alongside the actual observed values, not silently corrected.

For example, cash100 cents versus one share costing1900 cents fails even when the analyst says buy and reviewer says accept. The response exposes both numbers and sets blocked_by_rules. No extra model call is used to resolve disagreements.

`final_check.passed` means analyst output, reviewer acceptance and deterministic checks passed. `order_eligible` additionally requires a complete eligible application snapshot and an actionable buy/sell/close. Complete labeled test snapshots remain order-ineligible. Hold/wait can be valid reviewed decisions but never create orders. No code in this flow calls paper.execute or changes balances, positions, orders, fills, requests or P&L.

## Bounded calls and failure behavior

Each role has at most one call and a30-second wall-clock deadline; the reused HTTP client also retains its30-second socket timeout. There are no retries. If the analyst has no valid choice, the reviewer is skipped. A structurally valid but unaffordable analyst choice is still reviewed so both opinions and Python's overriding check can be inspected.

A daemon worker bounds each provider call. After timeout the request might still finish remotely, but its late return cannot update SQLite or trigger another call. This is not remote cancellation. The request finishes in at most roughly60 seconds of model waiting plus local validation/storage work. Verification clients allow75 seconds.

The analyst result commits before review; no database transaction spans network I/O. While review runs, status is review_pending, completed_at is null, reviewer call_count is recorded, and eligibility is false. A process interruption leaves that evidence and does not trigger automatic retry. The terminal update retains the same decision ID. No provisional single-role result is marked eligible.

Terminal outcomes include valid, review_rejected, blocked_by_rules, review_timeout, review_malformed_answer, review_refused, review_provider_error and review_configuration_error. Analyst failures retain their existing statuses with reviewer not_called and a skip reason. Named-answer type/name/category validation rejects malformed replies. Categorical outputs are retained for inspection, but provider error bodies, credential values and hidden reasoning are not saved. Unexpected provider exceptions become generic provider_error.

## Repeatable checks

```sh
python3 -m unittest backend.test_decision_review -v
python3 -m backend.review_check
```

The second command creates a disposable database and saves three fixed-reply cases: agreed policy-eligible buy, reviewer rejection, unaffordable buy accepted by both roles. It compares saved snapshots/results and proves all six paper tables unchanged. Fixtures retain test provenance; their execution eligibility stays false. The unit suite separately exercises the application eligibility branch in an isolated constructed fixture without executing it.

For one live two-call example, start the normal backend with the previously configured key in its Terminal:

```sh
MARKET_FEED_ENABLED=0 MARKET_DB_PATH=/private/tmp/market-decisions-live-check.sqlite3 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --ws websockets-sansio
```

Then run once:

```sh
python3 -m backend.review_check --live --database /private/tmp/market-decisions-live-check.sqlite3
```

This uses the prepared synthetic recorded fixture, creates one new snapshot, sends one endpoint request (up to two provider calls), compares both outputs and snapshot digests with SQLite and checks the ledger is unchanged. Do not describe this as live market verification. Observed live and controlled outcomes are kept separately in [verification.md](verification.md).
