# Part 4.1 submission checklist

| Requirement | Implementation and evidence | Remaining limitation |
|---|---|---|
| Yahoo live candles/WebSocket | receiver persists before FastAPI broadcast; Vue updates by timestamp; live-yahoo-candle-trace.json and screenshots | November12 capture, not a new live check |
| Aligned volume | daily counter deltas; browser shows52920estimated shares; volume-estimate.png | Sparse updates prevent exact minute totals; invalid baselines remain Unknown |
| Source, age, feed status | independent browser/upstream/freshness state | Socket alone is not fresh receipt |
| SQLite identity/time/revisions | raw decoded payload, immutable observations, deliveries, explicit revision links; recorder tests | Yahoo stable event/revision IDs not verified |
| Duplicate/out-of-order/completion | canonical deduplication, source ordering, receipt-time replay, completion metadata | Ambiguous same-time messages retained |
| Retrieval/replay | read-only receipt-prefix replay; browser video and replay-check.json | Replay is labeled recorded |
| Feed failure | upstream-disconnected.png and tests; current probe times out honestly | No current fresh update during30second probe |
| Docs/setup/init | README, AGENTS, design-pipeline, sqlite-schema, verification | No credentials needed forPart4.1 |
| Tests |90backend tests, build, full offline browser SmokeTest pass | Offline tests do not verify Yahoo availability |
| Report/repository/video | report.md, public repository,46.44second WebM with recorded-data label | Student must review disclosure and upload only report.md |

The report discloses partial volume accuracy and current live-check limits. The video demonstrates stored Yahoo data/replay and disconnected status, alongside separately linked historical live evidence. A fresh regular-session recording would strengthen the live-stream/volume demonstration; do not claim the replay video alone proves live receipt.
