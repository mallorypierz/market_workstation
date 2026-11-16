"""Start isolated browser SmokeTest services; Ctrl+C stops both children."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from backend.main import app
from backend import chart_analysis, decisions
from backend.recorder import connect


def controlled_provider(request):
    if request['questions'][0]['name']=='review_verdict':
        return {'answers':[{'name':'review_verdict','type':'choice','choice':'accept'}]}
    parts=request['input'][0]['content']
    assert [p['type'] for p in parts]==['input_json','input_image']
    snapshot=parts[0]['data']
    raw,width,height,meta=chart_analysis.decode_png(parts[1]['image_url'])
    assert meta['snapshot_id']==snapshot['snapshot_id'] and meta['sha256']==snapshot['sha256']
    expected={'2026-11-09T14:34:00Z':('buy','up'), '2026-11-09T14:36:00Z':('wait','down')}
    if snapshot['candle_timestamp'] not in expected:
        raise decisions.ProviderFailure('provider_error')
    action,cross=expected[snapshot['candle_timestamp']]
    db=connect()
    try:
        db.execute('CREATE TABLE IF NOT EXISTS chart_provider_calls (id INTEGER PRIMARY KEY,snapshot_id TEXT,png_sha256 TEXT,request_json TEXT)')
        db.execute('INSERT INTO chart_provider_calls(snapshot_id,png_sha256,request_json) VALUES(?,?,?)',
            (snapshot['snapshot_id'],hashlib.sha256(raw).hexdigest(),json.dumps(request)));db.commit()
    finally:db.close()
    return {'answers':[{'name':name,'type':'choice','choice':choice} for name,choice in
                       [('evidence','sufficient'),('action',action),('crossover',cross)]]}

app.state.decision_provider=controlled_provider


def main():
    from backend.decision_fixture import build
    folder=Path(tempfile.mkdtemp(prefix='chart-smoke-'));path=folder/'fixture.sqlite3'
    db=connect(path)
    try:build(db)
    finally:db.close()
    env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(folder/'settings.sqlite3'),
         'MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':'CONSTRUCTED chart crossover fixture · controlled provider',
         'VITE_API_TARGET':'http://127.0.0.1:8010'}
    env.pop('OPENAI_API_KEY',None)
    print(json.dumps({'database':str(path),'url':'http://127.0.0.1:5174','provider':'controlled-test',
        'operation':'Select 2026-11-09 14:34 UTC, Ask about chart, inspect frozen preview, Analyze frozen chart.',
        'expected':'buy / up / sufficient; Python up; no orders; captured PNG equals provider input and saved image.'}),flush=True)
    children=[]
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.chart_smoke:app','--host','127.0.0.1','--port','8010','--ws','websockets-sansio'],env=env))
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
