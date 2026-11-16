"""Supervised browser automation fixture. All observations and provider replies are constructed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime
from backend import main as server, paper, live
from backend.recorder import connect, record
from backend.chart_smoke import controlled_provider

app=server.app
app.state.decision_provider=controlled_provider
original_history=server.history_view

def clock():
    db=connect()
    try:return db.execute('SELECT stamp FROM fixture_clock').fetchone()[0]
    finally:db.close()

def history(**kw):
    kw['as_of']=kw.get('as_of') or clock()
    return original_history(**kw)

if os.environ.get('MARKET_AUTOMATION_TEST')=='1':
    paper.now=clock
    server.history_view=history
    live.history_view=history

@app.post('/api/fixture/advance')
def advance():
    db=connect()
    try:db.execute("UPDATE fixture_clock SET stamp='2026-11-09T14:35:01Z'");db.commit()
    finally:db.close()
    return {'constructed_clock':clock()}

@app.post('/api/fixture/price')
def price():
    db=connect();stamp='2026-11-09T14:35:10Z'
    try:
        db.execute('UPDATE fixture_clock SET stamp=?',(stamp,));db.commit()
        record(db,{'id':'AAPL','price':20,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)),'test_data':'CONSTRUCTED automation fixture'},stamp)
        paper.process_live(db)
        return paper.snapshot(db,'automation-test')
    finally:db.close()

def main():
    folder=Path(tempfile.mkdtemp(prefix='automation-smoke-'));path=folder/'fixture.sqlite3';db=connect(path)
    db.execute('CREATE TABLE fixture_clock(stamp TEXT)');db.execute("INSERT INTO fixture_clock VALUES('2026-11-09T14:34:55Z')");db.commit()
    for i,p in enumerate([13,10,7,13,19]):
        stamp=f'2026-11-09T14:{30+i}:50Z'
        record(db,{'id':'AAPL','price':p,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)),'test_data':'CONSTRUCTED automation fixture'},stamp)
    db.close()
    env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(folder/'settings.sqlite3'),'MARKET_AUTOMATION_TEST':'1','MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':'CONSTRUCTED automation fixture / controlled provider','VITE_API_TARGET':'http://127.0.0.1:8010'}
    env.pop('OPENAI_API_KEY',None)
    print(json.dumps({'database':str(path),'url':'http://127.0.0.1:5174','instructions':'Start paper automation, POST /api/fixture/advance, wait for pending order, POST /api/fixture/price; expect one fill, $980 and 1 share.'}),flush=True)
    children=[]
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.automation_smoke:app','--host','127.0.0.1','--port','8010','--ws','websockets-sansio'],env=env))
        children.append(subprocess.Popen(['npm','--prefix','frontend','run','dev','--','--port','5174'],env=env))
        for child in children:child.wait()
    except KeyboardInterrupt:pass
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__':main()
