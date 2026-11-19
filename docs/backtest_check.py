"""Real HTTP backtest persistence check with disposable input/account databases."""
from pathlib import Path
import json,os,signal,subprocess,sys,tempfile,urllib.request,urllib.error,sqlite3
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from docs.smoke_test import port,ready
from backend.recorder import connect
from backend.test_strategy import quote
from backend.test_sma import stamp
from backend.accounting_reference import source_digest


def stop(child):
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:child.wait(timeout=8)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()


def main():
    artifacts=ROOT/'test-results/backtest';artifacts.mkdir(parents=True,exist_ok=True)
    children=[];logs=[];result={'status':'failed','provider':'none','data':'constructed'}
    try:
        with tempfile.TemporaryDirectory(prefix='backtest-http-') as folder:
            path=Path(folder)/'source.sqlite3';db=connect(path)
            for i,p in enumerate([13,10,7,13,19]):quote(db,i,p)
            quote(db,5,100,False);quote(db,5,7);quote(db,6,1);quote(db,7,110,False)
            source_hash=source_digest(db);db.close()
            chosen=port();url=f'http://127.0.0.1:{chosen}'
            env={**os.environ,'MARKET_DB_PATH':str(path),'MARKET_SETTINGS_DB_PATH':str(Path(folder)/'settings.sqlite3'),
                 'MARKET_BACKTEST_DIR':str(Path(folder)/'runs'),'MARKET_FEED_ENABLED':'0'};env.pop('OPENAI_API_KEY',None)
            def api(route,body=None):
                req=urllib.request.Request(url+route,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
            first=None
            for phase in ['before','after']:
                log=(artifacts/(phase+'.log')).open('w');logs.append(log)
                child=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(chosen),'--ws','websockets-sansio'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child)
                ready(url+'/api/health',child)
                request={'run_id':'http-test','start':stamp(0),'end':stamp(10)}
                response=api('/api/backtests',request)
                assert response['status']=='completed'
                assert response['result']['ending_equity']==1010 and response['result']['total_return']==.01
                assert api('/api/backtests/http-test')==response
                if first is None:first=response
                else:assert response==first
                try:api('/api/backtests',{**request,'run_id':'invalid','short':3,'long':3})
                except urllib.error.HTTPError as error:assert error.code==422
                else:raise AssertionError('Expected invalid windows422')
                with sqlite3.connect(Path(folder)/'runs/http-test.sqlite3') as saved:
                    status,stored=saved.execute('SELECT status,result FROM backtest_run').fetchone()
                    assert status=='completed' and json.loads(stored)==response['result']
                    assert saved.execute("SELECT cash_cents FROM paper_accounts WHERE id='backtest'").fetchone()[0]==101000
                stop(child)
            db=connect(path);assert source_digest(db)==source_hash;assert db.execute("SELECT cash_cents FROM paper_accounts WHERE id='live'").fetchone()[0]==100000;db.close()
            (artifacts/'response.json').write_text(json.dumps(first,indent=2)+'\n')
            result.update(status='passed',before_after_equal=True,source_unchanged=True,production_account_untouched=True,ending_equity=1010,total_return=.01,max_drawdown=.099)
    except Exception as error:result['error']=f'{type(error).__name__}: {error}'
    finally:
        for child in reversed(children):stop(child)
        for log in logs:log.close()
        result['owned_processes_stopped']=all(c.poll() is not None for c in children)
        (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
