# Yahoo Finance subscription investigation

## Observed result — 2026-11-12 UTC (2026-11-11 EST)

Using Python 3.12.5, yfinance 1.8.0 and websockets 17.4 in the existing user-site environment. No Yahoo account, cookies or credentials were supplied. This is a bounded backend probe, separate from the synthetic chart and FastAPI request handlers.

First attempt with Python's default certificate settings failed with `SSLCertVerificationError`; socket did not open and receipt was unverified (exit 2). Retried with the installed certifi CA bundle via `SSL_CERT_FILE`, preserving certificate and hostname validation. No system trust settings were changed.

```sh
SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')" python3 -m backend.feed_probe --symbol AAPL --seconds 30
```

Observed socket open at `2026-11-12T03:40:32.221016Z`; subscription sent at `03:40:32.221203Z`. This confirms transport and a sent subscription, not a provider subscription acknowledgement. An actual AAPL update then arrived; worker exited 0 and closed the connection before the timeout.

| Field | Observation |
| --- | --- |
| ticker (`id`) | AAPL |
| price | 356.07 |
| source `time` raw | `"1794454833000"` |
| source time interpreted as Unix milliseconds | 2026-11-12T03:40:33Z |
| backend receipt UTC | 2026-11-12T03:40:34.802194Z |
| receipt minus source time | 1.802194 seconds |
| volume fields | None present; unavailable, not zero |
| other fields | exchange=NMS, quote_type=8, market_hours=4, change_percent=0.12372478, change=0.44000244, price_hint="2" |

[Observed decoded payload](evidence/yahoo-aapl-probe.json) contains only public market fields and probe timestamps. It is decoded provider data, not raw wire bytes. No credentials or headers were recorded.

## Time, identity and volume limitations

The observed 13-digit time converts to a source timestamp close to receipt when treated as milliseconds since Unix epoch; that provides empirical support for milliseconds for this message. The library schema declares `time` as an integer but does not itself document a time unit. The probe retains the raw string alongside the explicitly labeled interpretation. Backend receipt time is UTC captured at callback entry, independent of source time. The ~1.8 second difference suggests recent source data at this one receipt, not a guarantee of continuous streaming or exchange-level latency.

`id` identifies the ticker, not an individual event. No stable event identifier or revision sequence appeared in this observation. Do not use the ticker alone as an observation key. No identity/conflict or persistence behavior is implemented in this probe.

No volume field was delivered, so actual volume units, values, and update/reset behavior remain unverified. The installed protobuf schema exposes `day_volume`, `last_size`, `vol_24hr` and `vol_all_currencies`. The name `day_volume` suggests cumulative daily volume (for equity shares), not shares traded in this single update; this is an interpretation to verify against future observations, not an observed fact from this probe. Never sum successive `day_volume` values or treat them as per-minute volume. `last_size`, if present, is a distinct field and must not be silently substituted for candle volume. Missing fields must stay unavailable. The synthetic CSV's per-minute share-volume semantics do not establish live Yahoo volume semantics.

The raw market-hours code is retained without assigning a market-session label. Socket-open, message receipt, source freshness and market-session status are separate facts. One recent update proves backend receipt only; it does not establish frontend live updates, persistence, aggregation, completeness, revision behavior or replay. The Vue chart continues to show its explicitly labeled synthetic CSV sample.

## Probe bounds

`backend/feed_probe.py` uses yfinance.AsyncWebSocket, subscribes to one symbol, and stops after the first matching price update or the configured timeout. A parent process imposes a hard deadline of timeout + 15 seconds, including import/cleanup overhead; it kills the worker if necessary. Normal timeout/connection failure returns exit 2 and explicit unverified receipt status. Exceptions report their type only to avoid exposing credentials from network configuration. yfinance's internal reconnect loop cannot run beyond the parent deadline.

## References

- [Official WebSocket usage](https://ranaroussi.github.io/yfinance/reference/yfinance.websocket.html)
- [yfinance client implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/live.py)
- [Pricing protobuf schema](https://github.com/ranaroussi/yfinance/blob/main/yfinance/pricing.proto)

Installed client source and descriptor were also inspected; the links above track upstream and can change.


## Later live-dashboard observation (2026-11-12 regular session)

The integrated receiver subsequently stored actual observation #197 / receipt #199: AAPL price 356.24, source 2026-11-12T14:31:03Z, receipt 14:31:10.259674Z. Unlike the earlier bounded probe, this payload included day_volume="2011028" and last_size="80". Both raw values are preserved in [live trace evidence](evidence/live-yahoo-candle-trace.json). Their presence does not establish per-minute volume; Yahoo aggregation still returns null and the chart displays Unknown. Source arrival order was not identical to source-time order; the candle calculation retains source ordering. See verification.md for the actual database-to-chart comparison and upstream-disconnection behavior.
