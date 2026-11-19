"""Repeatable isolated strategy browser check; no installs or provider calls."""
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


def main():
    artifacts=ROOT/'test-results'/'strategy'
    artifacts.mkdir(parents=True,exist_ok=True)
    children=[]; logs=[]
    result={'status':'failed','market_data':'constructed','provider':'none'}
    try:
        with tempfile.TemporaryDirectory(prefix='strategy-browser-') as folder:
            path=Path(folder)/'fixture.sqlite3'; db=connect(path);
            from backend.test_strategy import quote
            quote(db,0,13);db.close()
            bp,fp=port(),port()
            env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(Path(folder)/'settings.sqlite3'),
                 'MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':'CONSTRUCTED strategy fixture — not live Yahoo',
                 'VITE_API_TARGET':f'http://127.0.0.1:{bp}','SMA_BASE_URL':f'http://127.0.0.1:{fp}','SMA_ARTIFACTS':str(artifacts),'STRATEGY_ROOT':str(ROOT),'STRATEGY_PYTHON':sys.executable}
            env.pop('OPENAI_API_KEY',None)
            for name,cmd,cwd,url in [
                ('backend',[sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp),'--ws','websockets-sansio'],ROOT,f'http://127.0.0.1:{bp}/api/health'),
                ('frontend',['node',str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(fp),'--strictPort'],ROOT/'frontend',env['SMA_BASE_URL'])]:
                log=(artifacts/(name+'.log')).open('w');logs.append(log)
                child=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child)
                ready(url,child)
            child=subprocess.Popen(['node','frontend/tests/strategy-check.mjs'],cwd=ROOT,env=env,start_new_session=True);children.append(child)
            if child.wait(timeout=120): raise RuntimeError('Strategy browser assertions failed; see browser.json')
            import sqlite3
            with sqlite3.connect(path) as check:
                assert check.execute("SELECT cash_cents FROM paper_accounts WHERE id='live'").fetchone()[0]==100000
                assert check.execute('SELECT COUNT(*) FROM paper_fills').fetchone()[0]==2
                result['sqlite_fills']=2
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
