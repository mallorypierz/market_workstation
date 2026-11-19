"""SQLite/API/Chromium reconciliation before and after real backend restart.

Creates three temporary accounts/databases; never uses the saved market DB.
"""
from pathlib import Path
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
from fractions import Fraction

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from docs.smoke_test import port,ready
from backend.recorder import connect
from backend.accounting_reference import build_case,EXPECTED,EQUITY,FIELDS,source_digest


def stop(child):
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:child.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL);child.wait()


def inspect(path,case):
    db=connect(path)
    try:
        rows=[dict(r) for r in db.execute("SELECT * FROM paper_pnl WHERE account_id='live' ORDER BY id")]
        assert [tuple(r[k] for k in FIELDS) for r in rows]==EXPECTED[case]
        equations=[]
        for row,wanted in zip(rows,EQUITY[case]):
            equity=None if row['price_exact'] is None and row['quantity'] else Fraction(row['cash_cents'])+row['quantity']*Fraction(row['price_exact'] or 0)
            assert equity==(None if wanted is None else Fraction(wanted))
            if equity is not None:
                total=Fraction(row['realized_exact'])+Fraction(row['unrealized_exact'])
                assert equity-100000==total==Fraction(row['total_exact'])
            equations.append({'equity_cents':None if equity is None else str(equity),'expected_equity_cents':wanted})
        orders=[dict(r) for r in db.execute("SELECT * FROM paper_orders WHERE account_id='live' ORDER BY id")]
        fills=[dict(r) for r in db.execute("SELECT f.*,o.symbol,o.side FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id WHERE o.account_id='live' ORDER BY f.id")]
        cash=db.execute("SELECT cash_cents FROM paper_accounts WHERE id='live'").fetchone()[0]
        assert cash>=0 and all(r[0]>=0 for r in db.execute('SELECT quantity FROM paper_positions'))
        return {'rows':rows,'orders':orders,'fills':fills,'cash_cents':cash,'equations':equations,'source_digest':source_digest(db)}
    finally:db.close()


def main():
    artifacts=ROOT/'test-results'/'accounting';artifacts.mkdir(parents=True,exist_ok=True)
    children=[];logs=[];result={'status':'failed','market_data':'constructed','provider':'none','cases':{}}
    try:
        with tempfile.TemporaryDirectory(prefix='accounting-browser-') as folder:
            for case in EXPECTED:
                path=Path(folder)/(case+'.sqlite3');db=connect(path);build_case(db,case);digest=source_digest(db);db.close()
                bp,fp=port(),port()
                env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(Path(folder)/(case+'-settings.sqlite3')),
                     'MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':f'CONSTRUCTED accounting {case} — not live Yahoo',
                     'VITE_API_TARGET':f'http://127.0.0.1:{bp}','ACCOUNTING_URL':f'http://127.0.0.1:{fp}','ACCOUNTING_CASE':case}
                env.pop('OPENAI_API_KEY',None)
                frontlog=(artifacts/(case+'-frontend.log')).open('w');logs.append(frontlog)
                front=subprocess.Popen(['node',str(ROOT/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',str(fp),'--strictPort'],cwd=ROOT/'frontend',env=env,stdout=frontlog,stderr=subprocess.STDOUT,start_new_session=True);children.append(front)
                ready(env['ACCOUNTING_URL'],front)
                snapshots=[]
                for phase in ['before','after']:
                    log=(artifacts/(case+'-'+phase+'-backend.log')).open('w');logs.append(log)
                    back=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp),'--ws','websockets-sansio'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(back)
                    ready(f'http://127.0.0.1:{bp}/api/health',back)
                    expected=inspect(path,case);assert expected['source_digest']==digest
                    expected_path=artifacts/(case+'-'+phase+'-sqlite.json');expected_path.write_text(json.dumps(expected,indent=2)+'\n')
                    browser_env={**env,'ACCOUNTING_PHASE':phase,'ACCOUNTING_EXPECTED':str(expected_path),'ACCOUNTING_OUTPUT':str(artifacts/(case+'-'+phase))}
                    test=subprocess.Popen(['node','frontend/tests/accounting-check.mjs'],cwd=ROOT,env=browser_env,start_new_session=True);children.append(test)
                    if test.wait(timeout=60):raise RuntimeError(f'{case}/{phase} browser comparison failed')
                    after=inspect(path,case);assert after==expected
                    snapshots.append(after)
                    stop(back)  # actual shutdown; next phase launches a fresh backend process on same DB/port
                assert snapshots[0]==snapshots[1]
                result['cases'][case]={'status':'passed','before_after_equal':True,'source_unchanged':True,'row_count':len(snapshots[0]['rows']),'expected':EXPECTED[case],'observed':[[r[k] for k in FIELDS] for r in snapshots[0]['rows']],'equations':snapshots[0]['equations']}
                stop(front)
            result['status']='passed'
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        for child in reversed(children):stop(child)
        for log in logs:log.close()
        result['owned_processes_stopped']=all(c.poll() is not None for c in children)
        (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
