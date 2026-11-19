"""Verify candidate source export, reusing installed dependencies; not a submitted-SHA checkout."""
from pathlib import Path
import hashlib,json,os,shutil,sqlite3,subprocess,sys,tempfile,urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from docs.smoke_test import port,ready
from docs.backtest_check import stop

def main():
 out=ROOT/'test-results/part42-checkout';out.mkdir(parents=True,exist_ok=True)
 result={'status':'failed','kind':'clean candidate source export, NOT committed checkout','dependencies':'existing Python environment and symlinked installed frontend/node_modules; no installation','commands':[]};child=None;log=None
 try:
  with tempfile.TemporaryDirectory(prefix='part42-source-') as tmp:
   base=Path(tmp);tree=base/'project';tree.mkdir()
   names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
   copied={}
   for name in sorted(set(filter(None,names))):
    source=ROOT/name
    if not source.is_file():continue
    target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);copied[name]=hashlib.sha256(source.read_bytes()).hexdigest()
   (tree/'frontend/node_modules').symlink_to(ROOT/'frontend/node_modules',target_is_directory=True)
   env={**os.environ,'MARKET_DB_PATH':str(base/'initialized.sqlite3'),'MARKET_SETTINGS_DB_PATH':str(base/'settings.sqlite3'),'MARKET_BACKTEST_DIR':str(base/'runs'),'MARKET_FEED_ENABLED':'0','CI':'true'};env.pop('OPENAI_API_KEY',None)
   def run(args,name,timeout=120):
    with (out/(name+'.log')).open('w') as output:r=subprocess.run(args,cwd=tree,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
    result['commands'].append({'command':' '.join(args),'exit_code':r.returncode,'log':name+'.log'})
    if r.returncode:raise RuntimeError(name+' failed')
   run([sys.executable,'-m','backend.recorder','init'],'init')
   with sqlite3.connect(base/'initialized.sqlite3') as db:
    result['initialized_tables']=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    assert db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0]==0
   bp=port();log=(out/'startup.log').open('w')
   child=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp)],cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   url=f'http://127.0.0.1:{bp}';ready(url+'/api/health',child)
   body={'run_id':'clean-startup','dataset':'aapl-2025-daily','timeframe':'1d','warmup_start':'2025-01-06T00:00:00Z','start':'2025-01-13T00:00:00Z','end':'2025-03-01T00:00:00Z'}
   request=urllib.request.Request(url+'/api/backtests',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(request,timeout=30) as response:saved=json.load(response)
   assert saved['result']['ending_equity']==999.64
   with sqlite3.connect(base/'runs/clean-startup.sqlite3') as db:assert json.loads(db.execute('SELECT result FROM backtest_run').fetchone()[0])==saved['result']
   stop(child);log.close();log=None
   run([sys.executable,'-m','unittest','discover','-s','backend','-p','test_*.py'],'python-tests')
   run(['npm','--prefix','frontend','run','build'],'build')
   run([sys.executable,'docs/smoke_test.py'],'smoke',timeout=360)
   smoke_dirs=sorted((tree/'test-results/smoke').iterdir());smoke=json.loads((smoke_dirs[-1]/'result.json').read_text());assert smoke['status']=='passed'
   result.update(status='passed',copied_file_count=len(copied),source_hashes={k:v for k,v in copied.items() if k.startswith(('backend/','frontend/src/','frontend/tests/'))},startup_equity=999.64,sqlite_saved_result_equal=True,smoke=smoke)
 except Exception as error:result['error']=f'{type(error).__name__}: {error}'
 finally:
  if child:stop(child)
  if log:log.close()
  result['owned_startup_process_stopped']=child is None or child.poll() is not None
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'},indent=2))
 return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
