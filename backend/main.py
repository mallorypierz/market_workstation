from fastapi import FastAPI, HTTPException, Response, Query, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import asyncio
import os
from typing import Literal
import sqlite3

from backend.timeframes import history_view
from backend.live import LiveFeed, stream_view
from backend.replay import recordings, replay_view
from backend.sma import with_sma, validate_windows
from backend.indicators import catalog
from backend.indicator_store import add_instance, list_instances, with_indicators
from pydantic import BaseModel, ConfigDict

class IndicatorRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str
    source: str
    timeframe: str
    name: str
    type: str
    settings: dict


def chart_view(view, short, long):
    return with_indicators(with_sma(view, short, long))

feed = LiveFeed()


@asynccontextmanager
async def lifespan(app):
    from backend import automation
    startup_db = paper.open_account_db()
    try: automation.startup(startup_db)
    finally: startup_db.close()
    if os.environ.get("MARKET_FEED_ENABLED", "1") == "1":
        await feed.start()
    yield
    await feed.stop()


app = FastAPI(title="Market Workstation", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/history")
def history(response: Response, symbol: str = "SAMPLE",
            timeframe: Literal["1m", "5m", "15m", "1h", "1d"] = "1m",
            source: Literal["sample", "yahoo"] = "sample", as_of: str | None = None,
            receipt_cutoff: int | None = Query(default=None, ge=0), include_metadata: bool = False, short: int = 2, long: int = 3):
    try:
        validate_windows(short, long)
        view = history_view(symbol=symbol, timeframe=timeframe, source=source,
                            as_of=as_of, receipt_cutoff=receipt_cutoff)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="History storage unavailable") from error
    response.headers["X-Data-Source"] = view["source"]
    response.headers["X-Timeframe"] = view["timeframe"]
    response.headers["X-Symbol"] = view["symbol"]
    return chart_view(view, short, long) if include_metadata else view["candles"]


@app.post("/api/feed/{action}")
async def control_feed(action: Literal["disconnect", "connect"]):
    # Local development controls; bind this unauthenticated app to loopback only.
    if action == "disconnect":
        await feed.stop()
    else:
        await feed.start()
    return feed.status()


@app.get("/api/recordings")
def saved_recordings():
    return recordings()


@app.get("/api/replay")
def replay(symbol: str, start: str, end: str,
           timeframe: Literal["1m", "5m", "15m", "1h", "1d"] = "1m",
           step: int = Query(default=0, ge=0), snapshot_cutoff: int | None = Query(default=None, ge=0), short: int = 2, long: int = 3):
    if feed.enabled or feed.connected:
        raise HTTPException(409, "Disconnect Yahoo before replay")
    try:
        validate_windows(short, long)
        return chart_view(replay_view(symbol=symbol, start=start, end=end, timeframe=timeframe,
                           step=step, snapshot_cutoff=snapshot_cutoff), short, long)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, "Recorded session unavailable") from error


@app.websocket("/api/stream")
async def candle_stream(socket: WebSocket, symbol: str = "AAPL", timeframe: str = "1m", source: str = "yahoo", short: int = 2, long: int = 3):
    from backend.timeframes import TIMEFRAMES
    await socket.accept()
    if timeframe not in TIMEFRAMES or (source, symbol) not in {("yahoo", "AAPL"), ("sample", "SAMPLE")}:
        await socket.close(code=1008, reason="Unsupported symbol, source or timeframe")
        return
    try:
        validate_windows(short, long)
    except ValueError as error:
        await socket.close(code=1008, reason=str(error))
        return
    sequence = 0
    previous = {}
    try:
        while True:
            view = chart_view(stream_view(feed, symbol, timeframe, source), short, long)
            current = {row["timestamp"]: row for row in view["candles"]}
            updates = [{"candle": candle, "completion": view["status"][stamp]}
                       for stamp, candle in current.items() if previous.get(stamp) != candle]
            # Every message carries an authoritative full view, including completion/status-only changes.
            # Reconnect and slow clients reconcile by timestamp; there is no snapshot/subscription gap.
            await asyncio.wait_for(socket.send_json({"type": "snapshot" if sequence == 0 else "candle_update",
                "sequence": sequence, "interval": timeframe, **view, "updates": updates,
                "removed": sorted(set(previous) - set(current))}), timeout=5)
            previous = current
            sequence += 1
            await asyncio.sleep(1)
    except (WebSocketDisconnect, asyncio.TimeoutError, OSError, RuntimeError):
        return


@app.get('/api/indicator-types')
def indicator_types():
    return catalog()


@app.get('/api/indicators')
def indicators(symbol: str, source: str, timeframe: str):
    try:
        return list_instances(symbol, source, timeframe)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, 'Indicator settings storage unavailable') from error


@app.post('/api/indicators', status_code=201)
def create_indicator(request: IndicatorRequest):
    try:
        return add_instance(request.symbol, request.source, request.timeframe,
                            request.name, request.type, request.settings)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, 'Indicator settings storage unavailable') from error


# All actions are local simulations; no broker is connected.
from backend import paper
from typing import Any
from contextlib import contextmanager

class PaperRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str
    action: str
    symbol: str = 'AAPL'
    quantity: Any = None
    account_id: str = 'live'

class PaperReplayRequest(BaseModel):
    account_id: str
    symbol: str = 'AAPL'
    start: str
    end: str
    snapshot_cutoff: int
    step: int = 0

class PaperAdvanceRequest(BaseModel):
    account_id: str
    step: int

@contextmanager
def paper_database():
    db = None
    try:
        db = paper.open_account_db()
        yield db
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, 'Paper account storage unavailable') from error
    finally:
        if db is not None: db.close()

@app.get('/api/paper/account')
def paper_account(account_id: str = 'live'):
    with paper_database() as db:
        if account_id == 'live': paper.process_live(db)
        db.execute('BEGIN')
        return {**paper.snapshot(db, account_id), 'data_label': os.environ.get('MARKET_DATA_LABEL', '')}

@app.post('/api/paper/actions')
def paper_action(request: PaperRequest):
    with paper_database() as db:
        return paper.execute(db, **request.model_dump())

@app.post('/api/paper/replay')
def paper_replay(request: PaperReplayRequest):
    if feed.enabled or feed.connected: raise HTTPException(409, 'Disconnect Yahoo before paper replay')
    with paper_database() as db:
        return paper.start_replay(db, **request.model_dump())

@app.post('/api/paper/replay/advance')
def paper_replay_advance(request: PaperAdvanceRequest):
    if feed.enabled or feed.connected: raise HTTPException(409, 'Disconnect Yahoo before paper replay')
    with paper_database() as db:
        return paper.advance_replay(db, request.account_id, request.step)


# Snapshot freezing and proposals never invoke the paper execution entry point.
from backend import decisions
from fastapi import Body

@contextmanager
def decision_database():
    try:
        with decisions.database() as db:
            yield db
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, 'Decision storage unavailable') from error

@app.post('/api/decision-snapshots', status_code=201)
def decision_snapshot(request: dict = Body(default={})):
    with decision_database() as db:
        return decisions.create_snapshot(db, request)

@app.get('/api/decision-snapshots/{snapshot_id}')
def saved_decision_snapshot(snapshot_id: str):
    with decision_database() as db:
        result = decisions.get_snapshot(db, snapshot_id)
        if result is None: raise HTTPException(404, 'Unknown snapshot')
        return result

@app.post('/api/decisions')
def request_decision(request: dict = Body(default={})):
    with decision_database() as db:
        from backend.decision_review import run
        return run(db, request, provider=getattr(app.state, "decision_provider", None))

@app.get('/api/decisions/{decision_id}')
def saved_decision(decision_id: str):
    with decision_database() as db:
        result = decisions.get_decision(db, decision_id)
        if result is None: raise HTTPException(404, 'Unknown decision')
        return result


@app.get('/api/chart-questions')
def chart_questions():
    from backend.chart_analysis import QUESTIONS
    return QUESTIONS

@app.get('/api/decisions/{decision_id}/image')
def decision_image(decision_id: str):
    from backend.chart_analysis import initialize
    with decision_database() as db:
        initialize(db)
        row=db.execute('SELECT png FROM decision_images WHERE decision_id=?',(decision_id,)).fetchone()
        if row is None: raise HTTPException(404,'No saved image for this decision')
        return Response(content=bytes(row[0]),media_type='image/png',headers={'Cache-Control':'no-store'})


from backend import automation
@contextmanager
def automation_database():
    with paper_database() as db:
        automation.initialize(db)
        yield db

@app.post('/api/automation/start')
def automation_start(request: dict = Body(default={})):
    with automation_database() as db: return automation.start(db,request)

@app.post('/api/automation/{identity}/stop')
def automation_stop(identity: str):
    with automation_database() as db: return automation.stop(db,identity)

@app.get('/api/automation/{identity}')
def automation_state(identity: str):
    with automation_database() as db:
        paper.process_live(db)
        return automation.state(db,identity)

@app.post('/api/automation/{identity}/candles')
def automation_candle(identity: str,request: dict = Body(default={})):
    with automation_database() as db: return automation.reserve(db,identity,request)

@app.post('/api/automation/jobs/{identity}/analyze')
def automation_analyze(identity: str,request: dict = Body(default={})):
    with automation_database() as db: return automation.submit(db,identity,request,provider=getattr(app.state,'decision_provider',None))

@app.post('/api/automation/jobs/{identity}/apply')
def automation_apply(identity: str):
    with automation_database() as db: return automation.apply(db,identity)

# Voice reads stored evidence without initializing or advancing the ledger.
from backend import voice

@app.get('/api/voice/decisions')
def voice_decisions():
    try:
        with voice.database() as db:return voice.choices(db)
    except (ValueError,sqlite3.Error):return []

@app.get('/api/voice/decisions/{identity}')
def voice_summary(identity: str):
    try:
        with voice.database() as db:return voice.summary(db,identity)
    except ValueError as error:raise HTTPException(404,str(error)) from None
    except sqlite3.Error:raise HTTPException(503,'Recorded voice evidence unavailable') from None

@app.post('/api/voice/sessions')
def voice_session(request: dict = Body(default={})):
    try:return voice.start(request)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    except voice.VoiceFailure as error:raise HTTPException(502,str(error)) from None
    except sqlite3.Error:raise HTTPException(503,'Recorded voice evidence unavailable') from None

@app.put('/api/indicators/{identity}')
def update_indicator(identity: int, request: dict = Body(default={})):
    from backend.indicator_store import update_window
    try:return update_window(identity, request.get('settings', {}))
    except ValueError as error:raise HTTPException(422,str(error)) from None
    except sqlite3.Error:raise HTTPException(503,'Indicator settings storage unavailable') from None
