"""Offline boundary fixtures, imported ONLY by the one-command SmokeTest."""
import hashlib
import json
import os
from datetime import datetime
from backend import main as server, paper, live, decisions, chart_analysis
from backend.recorder import connect, record

if os.environ.get('MARKET_SMOKE_TEST') != '1':raise RuntimeError('Smoke fixture requires explicit test environment')
app=server.app
original_history=server.history_view

def clock():
    db=connect()
    try:return db.execute('SELECT stamp FROM smoke_control').fetchone()[0]
    finally:db.close()

def history(**kw):
    kw['as_of']=kw.get('as_of') or clock()
    return original_history(**kw)

paper.now=clock
server.history_view=history
live.history_view=history
# An accidental upstream connect fails locally, never reaches Yahoo.
async def no_yahoo():raise RuntimeError('Yahoo is disabled by offline SmokeTest')
server.feed.start=no_yahoo

def quote(db,minute,price,second=50):
    stamp=f'2026-11-09T14:{minute:02}:{second:02}Z'
    payload={'id':'AAPL','price':price,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)), 'test_data':'OFFLINE SMOKETEST constructed events'}
    record(db,payload,stamp)
    return stamp

# Every required strategy signal is calculated by production SMA code.
ACTIONS={34:'buy',38:'buy',41:'sell',42:'buy',44:'close'}

def provider(request):
    parts=request['input'][0]['content'];review=request['questions'][0]['name']=='review_verdict'
    s=parts[0]['data']['snapshot'] if review else parts[0]['data']
    image=next(p['image_url'] for p in parts if p['type']=='input_image')
    raw,w,h,meta=chart_analysis.decode_png(image)
    assert s['symbol']=='AAPL' and s['interval']=='1m'
    assert meta=={'snapshot_id':s['snapshot_id'],'sha256':s['sha256'],'chart_range':s['capture_range']}
    assert s['chart']['candles'][-1]['timestamp']==s['candle_timestamp']==s['capture_range']['to']
    minute=int(s['candle_timestamp'][14:16]);signal=s['indicators']['at_candle']['signal'] or 'none'
    db=connect()
    try:
        mode=db.execute('SELECT provider_mode FROM smoke_control').fetchone()[0]
        prior=db.execute('SELECT sha256 FROM smoke_calls WHERE snapshot_id=? AND role=?',(s['snapshot_id'],'analyst')).fetchone()
        if review:assert prior and prior['sha256']==hashlib.sha256(raw).hexdigest()
        db.execute('INSERT INTO smoke_calls(snapshot_id,role,sha256,symbol,candle,width,height,mode) VALUES(?,?,?,?,?,?,?,?)',
            (s['snapshot_id'],'reviewer' if review else 'analyst',hashlib.sha256(raw).hexdigest(),s['symbol'],s['candle_timestamp'],w,h,mode));db.commit()
    finally:db.close()
    if mode=='failure':raise decisions.ProviderFailure('provider_error')
    if review:return {'answers':[{'name':'review_verdict','type':'choice','choice':'reject_unsupported_signal' if minute==42 else 'accept'}]}
    action=ACTIONS.get(minute,'hold' if s['account']['shares'] else 'wait')
    return {'answers':[{'name':k,'type':'choice','choice':v} for k,v in [('action',action),('crossover',signal),('evidence','sufficient')]]}

app.state.decision_provider=provider
# External model requests anywhere outside the controlled callback fail locally.
def no_model(*args,**kwargs):raise RuntimeError('Unstubbed model connection in offline test')
decisions.openai_request=no_model

@app.post('/api/smoke/control')
def control(request:dict):
    db=connect()
    try:
        if 'provider_mode' in request:
            assert request['provider_mode'] in ('success','failure')
            db.execute('UPDATE smoke_control SET provider_mode=?',(request['provider_mode'],));db.commit()
        if 'order_size' in request:
            assert request['order_size'] in (1,4)
            os.environ['MARKET_PAPER_ORDER_SIZE']=str(request['order_size'])
        if request.get('duplicate'):
            r=db.execute('SELECT decoded_message_json,receipt_time FROM deliveries ORDER BY receipt_id DESC LIMIT 1').fetchone()
            record(db,json.loads(r[0]),r[1])
        if 'minute' in request:
            minute=request['minute'];assert 35<=minute<=46
            if 'price' in request:quote(db,minute,request['price'],request.get('second',50))
            stamp=f'2026-11-09T14:{minute+1:02}:01Z' if request.get('complete') else f'2026-11-09T14:{minute:02}:{request.get("second",50):02}Z'
            db.execute('UPDATE smoke_control SET stamp=?',(stamp,));db.commit()
        paper.process_live(db)
        return {'clock':clock()}
    finally:db.close()

@app.get('/api/smoke/evidence')
def evidence():
    db=connect()
    try:
        return {'calls':[dict(r) for r in db.execute('SELECT * FROM smoke_calls')],
                'jobs':[dict(r) for r in db.execute('SELECT * FROM automation_jobs ORDER BY candle')],
                'orders':[dict(r) for r in db.execute('SELECT * FROM paper_orders')],
                'fills':[dict(r) for r in db.execute('SELECT * FROM paper_fills')],
                'account':paper.snapshot(db,'automation-test') if db.execute("SELECT 1 FROM paper_accounts WHERE id='automation-test'").fetchone() else None}
    finally:db.close()
