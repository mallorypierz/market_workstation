# Discuss a selected decision by voice

Explicitly authorized later-part extension; the original request is preserved in `prompts/13-add-live-speech.md`. This feature uses built-in browser WebRTC/media APIs and Python urllib/sqlite3. No installation or manifest change is required.

## Connection and evidence

Select a saved decision in **Discuss a recorded decision by voice**. The panel displays the symbol/cutoff, model-call label, proposal, reviewer verdict and whether a linked fill exists. Expand the evidence to inspect the exact facts. Start voice requests microphone permission from the click, attaches audio tracks, creates `oai-events`, creates/sets an offer, waits for ICE gathering, then posts `{decision_id,sdp}` to `/api/voice/sessions`.

FastAPI reads SQLite with `mode=ro` and `query_only=ON` inside a consistent read transaction. It loads the saved snapshot, visible role outputs, Python checks and decision-linked orders/fills/P&L/automation outcome. It does not call paper account initialization, advance pending orders or write a voice record. A no-fill result is stated as **no fill linked to this decision is recorded**; an analyst buy or reviewer accept is not proof of execution. Facts at decision time and later linked execution records remain separate.

Python sends its own configuration and offer to `https://api.openai.com/v1/live/sessions` using backend `OPENAI_API_KEY`. Model `gpt-live-1`, voice `marin`, store=false, client delegation with no tool handler. Instructions restrict conversation to the frozen summary and require acknowledging missing evidence; there is no trading API exposed to the voice transport. The client cannot supply instructions or fabricated account context. Generated speech remains probabilistic; compare claims with the visible evidence.

Vue applies the SDP answer and waits for `session.started`. Audio uses media tracks; transcript deltas appear as captions and do not prove audible playback. Follow-ups stay on the same peer connection/session. Selection is locked while active. The context is frozen at startup and does not silently include subsequent fills; restart voice to refresh it. Audio and summary are sent to OpenAI; the key stays on the server. The app does not persist microphone audio or transcripts.

End immediately stops local microphone tracks, requests `session.close`, and closes the connection after `session.closed` or a 15-second finalization timeout. Startup/network/permission failure, offline, pagehide and component removal release local media and close the peer connection. The startup deadline is 45 seconds, ICE wait 10 seconds and server HTTP timeout 30 seconds. If provider finalization is unconfirmed, the UI says so. If autoplay is blocked, use the audio controls. Bind the application to localhost; this is not a public authenticated service.

## Official documentation consulted

- [GPT-Live WebRTC guide](https://developers.openai.com/api/docs/guides/voice-webrtc?voice-api=live): offer/answer exchange and event readiness.
- [Session lifecycle and captions](https://developers.openai.com/api/docs/guides/live-conversations): transcript events and graceful close.

## Checks and live procedure

```sh
python3 -m unittest backend.test_voice -v
node --test frontend/src/voiceConnection.test.js
npm --prefix frontend run build
```

These use controlled inputs, fake media objects and a fake SDP provider. They verify read-only evidence, linked fill versus pending order, server-owned context, timeout/malformed response, microphone denial, startup cancellation, disconnected transport and close cleanup. They do not verify actual speech or hardware.

For a live check, run the backend in the Terminal holding OPENAI_API_KEY (do not put the key in commands, files or chat):

```sh
MARKET_FEED_ENABLED=0 MARKET_DB_PATH=/private/tmp/market-decisions-live-check.sqlite3 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --ws websockets-sansio
VITE_API_TARGET=http://127.0.0.1:8001 npm --prefix frontend run dev -- --port 5175 --strictPort
```

Open http://127.0.0.1:5175/. Select a recorded decision, inspect its evidence, click Start voice and allow microphone access. Wait for Connected and Microphone ACTIVE. Ask “What did the agents decide for this symbol?” then “What happened to the paper account?” in the same session. Record the actual spoken answers and compare proposal/review/fill/balances with SQLite. When no fill exists, check that speech does not claim one. Click End voice, confirm Microphone off and that the browser's microphone-in-use indicator clears. Also deny permission or interrupt a connection and confirm cleanup. Stop owned foreground services with Ctrl+C.

The selected database must already contain a saved decision. Live provider availability and audible answers are not established by a successful build or mocked tests. Record the observed live result in verification.md; never substitute captions or constructed audio for hearing the speaker.
