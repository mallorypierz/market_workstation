"""One-command offline browser SmokeTest. Never installs packages or edits source."""
from pathlib import Path
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def ready(url,child):
    until=time.monotonic()+40
    while time.monotonic()<until:
        if child.poll() is not None:raise RuntimeError(f'Service exited before ready: {url}')
        try:
            with urllib.request.urlopen(url,timeout=1) as r:
                if r.status==200:return
        except OSError:time.sleep(.15)
    raise RuntimeError(f'Service readiness timeout: {url}')

def seed(path, *, empty=False):
    from backend.recorder import connect,record
    from backend import paper
    from unittest.mock import patch
    db=connect(path)
    db.executescript("CREATE TABLE smoke_control(stamp TEXT,provider_mode TEXT); INSERT INTO smoke_control VALUES('2026-11-09T14:35:55Z','success'); CREATE TABLE smoke_calls(id INTEGER PRIMARY KEY,snapshot_id TEXT,role TEXT,sha256 TEXT,symbol TEXT,candle TEXT,width INTEGER,height INTEGER,mode TEXT);")
    with patch('backend.paper.now',return_value='2026-11-09T14:29:00Z'):paper.initialize(db)
    for i,p in enumerate([] if empty else [13,10,7,13,19,7]):
        stamp=f'2026-11-09T14:{30+i}:10Z'
        record(db,{'id':'AAPL','price':p,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)), 'test_data':'OFFLINE SMOKETEST constructed events'},stamp)
    if empty:
        db.execute("UPDATE smoke_control SET stamp='2026-11-09T14:29:00Z'");db.commit()
    db.close()

def main():
    def interrupted(signum, frame): raise KeyboardInterrupt('SmokeTest interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+str(os.getpid())
    artifacts=ROOT/'test-results'/'smoke'/run;artifacts.mkdir(parents=True)
    children=[];logs=[];result={'run':run,'status':'failed','provider':'controlled offline','market_data':'constructed'}
    with tempfile.TemporaryDirectory(prefix='market-smoke-') as folder:
        folder=Path(folder);dbpath=folder/'market.sqlite3'
        try:
            subprocess.run([sys.executable,str(ROOT/'docs/structure_check.py')],cwd=ROOT,check=True)
            cli=ROOT/'frontend/node_modules/@playwright/test/cli.js'
            if not cli.exists():raise RuntimeError('Playwright is missing. Follow approved setup in docs/smoke-test.md; SmokeTest never installs software.')
            seed(dbpath)
            seed(folder/'part42.sqlite3',empty=True)
            if os.environ.get('SMOKE_INJECT_PROVIDER_FAILURE') == '1':
                with sqlite3.connect(dbpath) as fault_db: fault_db.execute("UPDATE smoke_control SET provider_mode='failure'")
            backend_port,frontend_port=port(),port()
            while frontend_port==backend_port:frontend_port=port()
            env={**os.environ,'MARKET_SMOKE_TEST':'1','MARKET_AUTOMATION_TEST':'1','MARKET_FEED_ENABLED':'0',
                 'MARKET_DB_PATH':str(dbpath),'SMOKE_PART42_DB':str(folder/'part42.sqlite3'),
                 'MARKET_BACKTEST_DIR':str(folder/'backtests'),'MARKET_SETTINGS_DB_PATH':str(folder/'settings.sqlite3'),
                 'MARKET_DATA_LABEL':'OFFLINE SMOKETEST · constructed events and controlled provider',
                 'MARKET_PAPER_ORDER_SIZE':'4','VITE_API_TARGET':f'http://127.0.0.1:{backend_port}',
                 'SMOKE_BASE_URL':f'http://127.0.0.1:{frontend_port}','SMOKE_ARTIFACTS':str(artifacts)}
            env.pop('OPENAI_API_KEY',None)
            commands=[('backend',[sys.executable,'-m','uvicorn','backend.smoke_fixture:app','--host','127.0.0.1','--port',str(backend_port),'--ws','websockets-sansio']),
                      ('frontend',['node',str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(frontend_port),'--strictPort'])]
            for name,cmd in commands:
                log=(artifacts/(name+'.log')).open('w');logs.append(log)
                child=subprocess.Popen(cmd,cwd=ROOT if name=='backend' else ROOT/'frontend',env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child)
                ready(f'http://127.0.0.1:{backend_port}/api/health' if name=='backend' else env['SMOKE_BASE_URL'],child)
            test=subprocess.Popen(['node',str(cli),'test','--config=smoke.config.js'],cwd=ROOT/'frontend',env=env,start_new_session=True);children.append(test)
            code=test.wait(timeout=360)
            if code:raise RuntimeError(f'Browser assertions failed (exit {code}); see trace/screenshots/logs')
            db=sqlite3.connect(dbpath);db.row_factory=sqlite3.Row
            account=dict(db.execute("SELECT cash_cents FROM paper_accounts WHERE id='automation-test'").fetchone())
            quantity=db.execute("SELECT COALESCE(SUM(quantity),0) FROM paper_positions WHERE account_id='automation-test'").fetchone()[0]
            fills=db.execute('SELECT count(*) FROM paper_fills').fetchone()[0]
            mark=dict(db.execute("SELECT * FROM paper_pnl WHERE account_id='automation-test' ORDER BY id DESC LIMIT 1").fetchone())
            assert (account['cash_cents'],quantity,fills,mark['realized_exact'],mark['unrealized_exact'])==(102500,0,3,'2500','0'),(account,quantity,fills,mark)
            result.update(status='passed',cash=1025,shares=quantity,fills=fills,realized=25,unrealized=0,
                          provider_calls=db.execute('SELECT count(*) FROM smoke_calls').fetchone()[0])
            db.close()
            from docs.smoke_part42 import verify
            result['part42']=verify(folder,artifacts)
        except BaseException as error:
            result['status']='failed'
            result['error']=f'{type(error).__name__}: {error}';print(result['error'],file=sys.stderr)
        finally:
            for child in reversed(children):
                # Whole owned process groups, including browser/Vite descendants.
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            for child in reversed(children):
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait()
            for log in logs:log.close()
            if dbpath.exists():
                source=sqlite3.connect(dbpath);target=sqlite3.connect(artifacts/'evidence.sqlite3');source.backup(target);target.close();source.close()
            if (folder/'part42.sqlite3').exists():
                shutil.copy2(folder/'part42.sqlite3',artifacts/'part42.sqlite3')
            if (folder/'backtests').exists():
                shutil.copytree(folder/'backtests',artifacts/'backtests')
            result['owned_processes_stopped']=all(c.poll() is not None for c in children)
            (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({**result,'artifacts':str(artifacts)},indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
