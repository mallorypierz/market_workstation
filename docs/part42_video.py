"""Record a captioned actual-app Part4.2 demonstration using installed Playwright."""
from pathlib import Path
import os,json,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from docs.smoke_test import port,ready
from docs.backtest_check import stop
from backend.recorder import connect
from backend.test_strategy import quote
from backend import backtest

def main():
 out=ROOT/'test-results/part42-video';out.mkdir(parents=True,exist_ok=True);children=[];logs=[]
 try:
  with tempfile.TemporaryDirectory(prefix='part42-video-') as tmp:
   tmp=Path(tmp);source=tmp/'constructed-demo.sqlite3';db=connect(source)
   for i,p in enumerate([13,10,7,13,19]):quote(db,i,p)
   quote(db,5,100,False);quote(db,5,7);quote(db,6,1);quote(db,7,110,False);db.close()
   os.environ['MARKET_BACKTEST_DIR']=str(tmp/'runs')
   first=backtest.run('demo-constructed',{'start':'2026-11-09T14:30:00Z','end':'2026-11-09T14:40:00Z'},source=source)
   real=backtest.run('demo-yahoo-daily',{'warmup_start':'2025-01-06T00:00:00Z','start':'2025-01-13T00:00:00Z','end':'2025-03-01T00:00:00Z','timeframe':'1d'},bars=json.loads((ROOT/'docs/evidence/aapl-2025-daily.json').read_text()))
   (out/'runs.json').write_text(json.dumps({'constructed':first,'yahoo_daily':real},indent=2))
   bp,fp=port(),port();env={**os.environ,'MARKET_DB_PATH':str(source),'MARKET_SETTINGS_DB_PATH':str(tmp/'settings.sqlite3'),'MARKET_FEED_ENABLED':'0','MARKET_DATA_LABEL':'CONSTRUCTED recording fixture (not live Yahoo)','VITE_API_TARGET':f'http://127.0.0.1:{bp}','DEMO_URL':f'http://127.0.0.1:{fp}','DEMO_OUT':str(out)};env.pop('OPENAI_API_KEY',None)
   for name,command,cwd,url in [('backend',[sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(bp)],ROOT,env['VITE_API_TARGET']+'/api/health'),('frontend',['node','node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',str(fp),'--strictPort'],ROOT/'frontend',env['DEMO_URL'])]:
    log=(out/(name+'.log')).open('w');logs.append(log);child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append(child);ready(url,child)
   child=subprocess.Popen(['node','frontend/tests/part42-video.mjs'],cwd=ROOT,env=env,start_new_session=True);children.append(child)
   if child.wait(timeout=90):raise RuntimeError('Video browser failed')
 finally:
  for child in reversed(children):stop(child)
  for log in logs:log.close()
  (out/'cleanup.json').write_text(json.dumps({'owned_processes_stopped':all(c.poll() is not None for c in children)}))
if __name__=='__main__':main()
