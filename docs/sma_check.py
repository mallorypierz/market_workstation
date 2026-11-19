"""Repeatable isolated SMA browser/reference check; no installs or provider calls."""
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docs.smoke_test import port, ready
from backend.recorder import connect
from backend.test_sma import seed, stamp, CLOSES
from backend.sma_reference import LONG_CLOSES, reference
from backend.sma import sma


def main():
    artifacts=ROOT/'test-results'/'sma'
    artifacts.mkdir(parents=True,exist_ok=True)
    children=[]; logs=[]
    result={'status':'failed','market_data':'constructed','provider':'none'}
    try:
        references=[]
        for prices,short,long in [(CLOSES,2,3),(LONG_CLOSES,3,5)]:
            candles=[{'timestamp':stamp(i),'close':p} for i,p in enumerate(prices)]
            status={c['timestamp']:{'complete':True} for c in candles}
            expected=reference(candles,status,short,long)
            actual=sma(candles,status,short,long)['values']
            assert actual==expected
            references.append({'closes':prices,'short':short,'long':long,'expected':expected,'observed':actual})
        (artifacts/'reference.json').write_text(json.dumps({'oracle':'SQLite integer window SUM/COUNT; exact cross-product signs','tolerance':0,'datasets':references},indent=2)+'\n')
        with tempfile.TemporaryDirectory(prefix='sma-browser-') as folder:
            path=Path(folder)/'fixture.sqlite3'; db=connect(path);seed(db);db.close()
            bp,fp=port(),port()
            env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(Path(folder)/'settings.sqlite3'),
                 'MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':'CONSTRUCTED SMA reference — not live Yahoo',
                 'VITE_API_TARGET':f'http://127.0.0.1:{bp}','SMA_BASE_URL':f'http://127.0.0.1:{fp}','SMA_ARTIFACTS':str(artifacts)}
            env.pop('OPENAI_API_KEY',None)
            for name,cmd,cwd,url in [
                ('backend',[sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp),'--ws','websockets-sansio'],ROOT,f'http://127.0.0.1:{bp}/api/health'),
                ('frontend',['node',str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(fp),'--strictPort'],ROOT/'frontend',env['SMA_BASE_URL'])]:
                log=(artifacts/(name+'.log')).open('w');logs.append(log)
                child=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child)
                ready(url,child)
            child=subprocess.Popen(['node','frontend/tests/sma-check.mjs'],cwd=ROOT,env=env,start_new_session=True);children.append(child)
            if child.wait(timeout=90): raise RuntimeError('SMA browser assertions failed; see browser.json')
            result['status']='passed'
    except Exception as error:
        result['error']=str(error)
    finally:
        for child in reversed(children):
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        for child in reversed(children):
            try:child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL);child.wait()
        for log in logs:log.close()
        result['owned_processes_stopped']=all(c.poll() is not None for c in children)
        (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
