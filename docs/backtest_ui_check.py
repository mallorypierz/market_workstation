"""Actual Chromium interactions, real backend outage/restart, isolated SQLite reconciliation."""
from pathlib import Path
import os,json,subprocess,sys,tempfile,sqlite3
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from docs.smoke_test import port,ready
from docs.backtest_check import stop
from backend.recorder import connect
from backend.accounting_reference import source_digest

def main():
 out=ROOT/'test-results/backtest-ui';out.mkdir(parents=True,exist_ok=True)
 children=[];logs=[];result={'status':'failed','data':'real saved Yahoo daily bars; disposable empty receipt database','provider':'none'}
 try:
  with tempfile.TemporaryDirectory(prefix='backtest-ui-') as folder:
   folder=Path(folder);source=folder/'source.sqlite3';db=connect(source);digest=source_digest(db);db.close();bp,fp=port(),port()
   env={**os.environ,'MARKET_DB_PATH':str(source),'MARKET_SETTINGS_DB_PATH':str(folder/'settings.sqlite3'),'MARKET_BACKTEST_DIR':str(folder/'runs'),'MARKET_FEED_ENABLED':'0','VITE_API_TARGET':f'http://127.0.0.1:{bp}','BT_URL':f'http://127.0.0.1:{fp}','BT_OUT':str(out)};env.pop('OPENAI_API_KEY',None)
   def start(command,cwd,name):
    log=(out/(name+'.log')).open('w');logs.append(log);p=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(p);return p
   front=start(['node','node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',str(fp),'--strictPort'],ROOT/'frontend','frontend');ready(env['BT_URL'],front)
   def backend():
    p=start([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp)],ROOT,'backend');ready(env['VITE_API_TARGET']+'/api/health',p);return p
   back=backend();snapshots=[]
   for phase in ['before','failure','after']:
    if phase=='failure':stop(back)
    if phase=='after':back=backend()
    p=subprocess.Popen(['node','frontend/tests/backtest-check.mjs'],cwd=ROOT,env={**env,'BT_PHASE':phase},start_new_session=True);children.append(p)
    if p.wait(timeout=60):raise AssertionError('Browser '+phase+' failed')
    if phase!='failure':
     response=json.loads((out/'response.json').read_text());path=folder/'runs'/(response['run_id']+'.sqlite3')
     with sqlite3.connect(path) as db:
      stored=json.loads(db.execute('SELECT result FROM backtest_run').fetchone()[0]);assert stored==response['result']
      cash=db.execute("SELECT cash_cents FROM paper_accounts WHERE id='backtest'").fetchone()[0];fills=db.execute('SELECT COUNT(*) FROM paper_fills').fetchone()[0]
      assert cash==99964 and fills==10;snapshots.append({'cash_cents':cash,'fills':fills,'result':stored})
   assert snapshots[0]==snapshots[1]
   db=connect(source);assert source_digest(db)==digest;db.close()
   result.update(status='passed',before_after_equal=True,source_unchanged=True,cash_cents=99964,fills=10,return_value=response['result']['total_return'],max_drawdown=response['result']['max_drawdown'],dataset_sha256=response['metadata']['dataset_sha256'],run_id=response['run_id'])
 except Exception as e:result['error']=f'{type(e).__name__}: {e}'
 finally:
  for p in reversed(children):stop(p)
  for log in logs:log.close()
  result['owned_processes_stopped']=all(p.poll() is not None for p in children);(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
