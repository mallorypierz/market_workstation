"""Frozen receipt/bar backtests, isolated SQLite ledger, no model or real orders."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from backend import paper, pnl
from backend.recorder import connect, database_path, record
from backend.candles import aggregate, utc
from backend.timeframes import resample, TIMEFRAMES, calendar_for
from backend.sma import sma, validate_windows
from backend.strategy import choose_action

ROOT=Path(__file__).resolve().parents[1]
POLICY='sma-one-share-v1'
ASSUMPTIONS={'fees':0,'spread':0,'slippage':0,'fill':'full; positive price rounded HALF_UP to cents',
 'sizing':'one share when flat; close on down; no borrowing/shorting/pyramiding',
 'receipt_execution':'first later eligible receipt; duplicates/corrections not executable; stale/off-session quotes may fill',
 'bar_execution':'next supplied session open only; OHLC available only at session close; no original receipt/revision history',
 'valuation':'last positive known completed close, even if older than fill; unavailable if none; no forced liquidation',
 'actions':'price return only; no dividends credited; reject bar datasets containing splits',
 'missing':'no fabricated bars; windows span supplied completed candles',
 'metrics':'initial equity plus each evaluation receipt/bar close; max drawdown from running peak; no annualization'}


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def iso(value):return utc(value).isoformat().replace('+00:00','Z')
def root():return Path(os.environ.get('MARKET_BACKTEST_DIR',str(ROOT/'backend/data/backtests'))).resolve()
def path_for(identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}',identity):raise ValueError('Invalid backtest ID')
    return root()/(identity+'.sqlite3')


def normalize(request):
    short=request.get('short',2);long=request.get('long',3);validate_windows(short,long)
    cash=request.get('initial_cash_cents',100000)
    if type(cash) is not int or not 0<cash<=10**12:raise ValueError('Initial cash must be positive integer cents, at most 1e12')
    if request.get('symbol','AAPL')!='AAPL':raise ValueError('Backtests currently support AAPL')
    timeframe=request.get('timeframe','1m')
    if timeframe not in TIMEFRAMES:raise ValueError('Unsupported timeframe')
    start=iso(request['start']);end=iso(request['end']);warm=iso(request.get('warmup_start',start))
    if not utc(warm)<=utc(start)<utc(end):raise ValueError('Require warmup_start <= start < end (UTC)')
    cutoff=request.get('snapshot_cutoff')
    if cutoff is not None and (type(cutoff) is not int or cutoff<0):raise ValueError('Invalid receipt cutoff')
    return {'symbol':'AAPL','timeframe':timeframe,'short':short,'long':long,'initial_cash_cents':cash,
            'start':start,'end':end,'warmup_start':warm,'snapshot_cutoff':cutoff,'policy':POLICY,'size':1}


def freeze_receipts(source,config):
    path=Path(source).resolve()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        ceiling=db.execute('SELECT COALESCE(MAX(receipt_id),0) FROM deliveries').fetchone()[0]
        ceiling=min(ceiling,config['snapshot_cutoff']) if config['snapshot_cutoff'] is not None else ceiling
        rows=[dict(r) for r in db.execute('''SELECT d.* FROM deliveries d JOIN observations o USING(observation_id)
             WHERE o.source='yahoo' AND o.ticker=? AND d.receipt_id<=? ORDER BY d.receipt_id''',(config['symbol'],ceiling))
              if utc(config['warmup_start'])<=utc(r['receipt_time'])<utc(config['end'])]
        ids={r['observation_id'] for r in rows};receipts={r['receipt_id'] for r in rows}
        observations=[dict(r) for r in db.execute('SELECT * FROM observations ORDER BY observation_id') if r['observation_id'] in ids]
        revisions=[dict(r) for r in db.execute('SELECT * FROM revisions ORDER BY revision_id') if r['identified_at_receipt_id'] in receipts and r['earlier_id'] in ids and r['later_id'] in ids]
    return {'kind':'recorded_yahoo_receipts','provenance':{'source':'saved Yahoo decoded deliveries','source_file':path.name,'frozen_at':paper.now(),
            'receipt_cutoff':ceiling,'original_receipt_history':True,'adjustments':'as received; no adjustment or corporate-action model'},
            'observations':observations,'deliveries':rows,'revisions':revisions}


def freeze_bars(document,config):
    if config['timeframe']!='1d':raise ValueError('Historical daily bars require timeframe 1d')
    if document.get('kind') not in ('yahoo_daily_bars','synthetic_daily_bars') or document.get('symbol')!='AAPL':raise ValueError('Require explicitly labeled AAPL daily data')
    bars=[];seen=set()
    for item in document['bars']:
        date=item['date'];cal=calendar_for('XNAS',int(date[:4]))
        if date not in cal.schedule.index:raise ValueError('Bar is outside exchange sessions')
        opening=iso(cal.schedule.loc[date]['open'].to_pydatetime());closing=iso(cal.schedule.loc[date]['close'].to_pydatetime())
        if not utc(config['warmup_start'])<=utc(opening)<utc(config['end']):continue
        if date in seen:raise ValueError('Duplicate daily bar')
        seen.add(date)
        prices=[item[k] for k in ('open','high','low','close')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in prices):raise ValueError('Invalid bar prices')
        if not item['low']<=min(item['open'],item['close'])<=max(item['open'],item['close'])<=item['high']:raise ValueError('Invalid OHLC range')
        if item.get('splits',0):raise ValueError('Stock splits unsupported; choose a split-free period')
        bars.append({**item,'opening':opening,'closing':closing})
    bars.sort(key=lambda b:b['opening'])
    return {'kind':document['kind'],'provenance':{k:v for k,v in document.items() if k!='bars'},'bars':bars}


def _insert(db,table,rows):
    if not rows:return
    keys=list(rows[0]);db.executemany(f'INSERT INTO {table} ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',[[r[k] for k in keys] for r in rows])


def evaluate(db,config,data):
    account_id='backtest'
    db.execute('INSERT INTO paper_accounts VALUES(?,?,?,?,?,?,?,?)',(account_id,'backtest',config['initial_cash_cents'],config['initial_cash_cents'],config['start'],0,0,None));db.commit()
    trace=[];curve=[{'time':config['start'],'receipt_id':None,'cash_cents':config['initial_cash_cents'],'shares':0,'equity':config['initial_cash_cents']/100,'equity_exact_cents':str(config['initial_cash_cents']),'mark':None,'kind':'initial'}]
    last='';complete_count=0;eval_steps=0;warm_count=0
    def decide(view,receipt,clock):
        nonlocal last,complete_count,warm_count
        candles={c['timestamp']:c for c in view['candles']}
        for value in sma(view['candles'],view['status'],config['short'],config['long'])['values']:
            stamp=value['timestamp']
            if stamp<=last or not view['status'][stamp]['complete']:continue
            last=stamp
            if utc(stamp)<utc(config['start']):warm_count+=1;continue
            complete_count+=1
            acct=paper.account(db,account_id);held=paper.shares(db,account_id,'AAPL')
            pending=db.execute("SELECT 1 FROM paper_orders WHERE account_id=? AND status='pending'",(account_id,)).fetchone()
            action,reason=choose_action(value,acct['cash_cents'],held,bool(pending),candles[stamp]['close'])
            order=None
            if action!='none':
                order=paper.execute(db,request_id=f'bt:{stamp}',action=action,quantity=1 if action=='buy' else None,account_id=account_id,_in_transaction=True)
                db.execute('UPDATE paper_orders SET submitted_at=? WHERE id=?',(clock,order['id']))
            trace.append({**value,'receipt_id':receipt,'decision_time':clock,'candle_close':candles[stamp]['close'],
                          'action':action,'reason':reason,'order_id':order['id'] if order else None,'cash_before':acct['cash_cents'],'shares_before':held})
    def mark(view,receipt,clock):
        nonlocal eval_steps
        eval_steps+=1
        candidates=[c for c in view['candles'] if view['status'][c['timestamp']]['complete'] and paper.price_cents(c['close']) is not None]
        chosen=candidates[-1] if candidates else None
        held=paper.shares(db,account_id,'AAPL')
        if held:
            pnl.append(db,account_id=account_id,symbol='AAPL',key=f'backtest-mark:{receipt}',kind='backtest completed close',event_time=clock,
                       price=Fraction(str(chosen['close']))*100 if chosen else None,
                       price_time=view['status'][chosen['timestamp']]['interval_end'] if chosen else None,
                       price_source='last usable known completed close (interval end)',knowledge_receipt=receipt,
                       candle_timestamp=chosen['timestamp'] if chosen else None)
        cash=paper.account(db,account_id)['cash_cents']
        equity=Fraction(cash) if not held else Fraction(cash)+held*Fraction(str(chosen['close']))*100 if chosen else None
        curve.append({'time':clock,'receipt_id':receipt,'cash_cents':cash,'shares':held,'equity':None if equity is None else float(equity/100),
                      'equity_exact_cents':None if equity is None else str(equity),'mark':chosen,'kind':'completed-close valuation'})
    if data['kind']=='recorded_yahoo_receipts':
        for table in ('observations','deliveries','revisions'):_insert(db,table,data[table])
        db.commit();clock=config['warmup_start']
        for row in data['deliveries']:
            clock=iso(max(utc(clock),utc(row['receipt_time'])))
            if utc(clock)>=utc(config['end']):break
            db.execute('BEGIN IMMEDIATE')
            enriched=dict(row,ticker='AAPL',source='yahoo')
            if utc(clock)>=utc(config['start']):paper._fill_receipt(db,paper.account(db,account_id),enriched)
            db.execute('UPDATE paper_accounts SET cursor=? WHERE id=?',(row['receipt_id'],account_id))
            minutes=aggregate(db,'AAPL',as_of=clock,receipt_cutoff=row['receipt_id'])
            view=resample(minutes['candles'],symbol='AAPL',timeframe=config['timeframe'],as_of=clock,minute_status=minutes['status'])
            decide(view,row['receipt_id'],clock)
            if utc(clock)>=utc(config['start']):mark(view,row['receipt_id'],clock)
            db.commit()
    else:
        known=[];status={}
        for bar in data['bars']:
            # Open is the sole executable quote; no current high/low/close is exposed yet.
            for phase,time in [('open',bar['opening']),('close',bar['closing'])]:
                if utc(time)>=utc(config['end']):continue
                stored=record(db,{'id':'AAPL','time':str(int(utc(time).timestamp()*1000)),'price':bar[phase],
                                 'adapter':'historical daily bar '+phase},time,source='historical-yahoo-bars' if data['kind']=='yahoo_daily_bars' else 'synthetic-daily-bars')
                receipt=stored['receipt_id'];db.execute('BEGIN IMMEDIATE')
                if phase=='open' and utc(time)>=utc(config['start']):
                    row=dict(db.execute('SELECT d.*,o.ticker,o.source FROM deliveries d JOIN observations o USING(observation_id) WHERE receipt_id=?',(receipt,)).fetchone())
                    paper._fill_receipt(db,paper.account(db,account_id),row,source=row['source'])
                db.execute('UPDATE paper_accounts SET cursor=? WHERE id=?',(receipt,account_id))
                if phase=='close':
                    known.append({'timestamp':bar['opening'],**{k:bar[k] for k in ('open','high','low','close')},'volume':bar.get('volume')})
                    status[bar['opening']]={'complete':True,'interval_end':bar['closing']}
                    view={'candles':known,'status':status};decide(view,receipt,time)
                    if utc(time)>=utc(config['start']):mark(view,receipt,time)
                db.commit()
        # If selection ends after an open but before its close, value at previously known close.
        if data['bars'] and paper.account(db,account_id)['cursor'] and curve[-1]['receipt_id']!=paper.account(db,account_id)['cursor']:
            receipt=paper.account(db,account_id)['cursor'];time=db.execute('SELECT receipt_time FROM deliveries WHERE receipt_id=?',(receipt,)).fetchone()[0]
            if utc(time)>=utc(config['start']):
                mark({'candles':known,'status':status},receipt,time);db.commit()
    account=paper.snapshot(db,account_id)
    peak=Fraction(config['initial_cash_cents']);drawdown=Fraction(0);unknown=False
    for row in curve:
        if row['equity_exact_cents'] is None:unknown=True;continue
        equity=Fraction(row['equity_exact_cents']);peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak)
    ending=curve[-1]['equity']
    exact_return=None if curve[-1]['equity_exact_cents'] is None else (Fraction(curve[-1]['equity_exact_cents'])-config['initial_cash_cents'])/config['initial_cash_cents']
    orders={o['id']:o for o in account['orders']};fills={f['order_id']:f for f in account['fills']}
    for event in trace:
        event['order']=orders.get(event['order_id']);event['fill']=fills.get(event['order_id'])
    return {'account':account,'decisions':trace,'equity_curve':curve,'ending_equity':ending,
            'total_return':None if exact_return is None else float(exact_return),'total_return_exact':None if exact_return is None else str(exact_return),
            'max_drawdown':None if unknown else float(drawdown),'max_drawdown_exact':None if unknown else str(drawdown),
            'pending_orders':[o for o in account['orders'] if o['status']=='pending'],'open_positions':[p for p in account['positions'] if p['quantity']],
            'sample':{'warmup_completed_candles':warm_count,'evaluation_completed_candles':complete_count,'valuation_steps':eval_steps,'fills':len(account['fills'])},
            'warnings':(['No evaluated candles'] if not complete_count else [])+(['SMA warm-up incomplete for some decisions'] if any(e['reason']=='SMA warm-up' for e in trace) else [])}


def code_version():
    hashes={name:hashlib.sha256((ROOT/'backend'/name).read_bytes()).hexdigest() for name in ['backtest.py','strategy.py','sma.py','indicators.py','paper.py','pnl.py','candles.py','timeframes.py','recorder.py']}
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    import importlib.metadata
    import platform
    return {'git_head':commit,'source_sha256':hashes,'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
            'packages':{name:importlib.metadata.version(name) for name in ['yfinance','exchange-calendars']},'note':'source hashes identify uncommitted changes; HEAD alone may not'}


def chart_snapshot(db,config,data):
    """Presentation only: final known input view, never execute or revise trades."""
    if data['kind']=='recorded_yahoo_receipts':
        rows=data['deliveries']
        clock=iso(max([utc(config['warmup_start'])]+[utc(r['receipt_time']) for r in rows]))
        cutoff=max([0]+[r['receipt_id'] for r in rows])
        minutes=aggregate(db,'AAPL',as_of=clock,receipt_cutoff=cutoff)
        view=resample(minutes['candles'],symbol='AAPL',timeframe=config['timeframe'],as_of=clock,minute_status=minutes['status'])
    else:
        bars=[b for b in data['bars'] if utc(b['closing'])<utc(config['end'])]
        view={'candles':[{'timestamp':b['opening'],**{k:b[k] for k in ('open','high','low','close')},'volume':b.get('volume')} for b in bars],
              'status':{b['opening']:{'complete':True,'interval_end':b['closing']} for b in bars}}
    return {**view,'sma':sma(view['candles'],view['status'],config['short'],config['long']),
            'label':'Final known data including warm-up; corrections may differ from frozen trading decisions'}


def read(identity):
    path=path_for(identity)
    if not path.exists():raise ValueError('Unknown backtest')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT metadata,status,result,error,frozen_input FROM backtest_run WHERE id=1').fetchone()
        result=json.loads(row[2]) if row[2] else None
        if result is not None and 'chart' not in result:
            result['chart']=chart_snapshot(db,json.loads(row[0])['config'],json.loads(row[4]))
    return {'run_id':identity,'metadata':json.loads(row[0]),'status':row[1],'result':result,'error':row[3]}


def run(identity,request,*,source=None,bars=None,reject_empty=False):
    config=normalize(request);path=path_for(identity)
    descriptor={'config':config,'source':str(Path(source or database_path()).resolve()) if bars is None else 'bars','bars_hash':digest(bars) if bars is not None else None}
    if path.exists():
        saved=read(identity)
        if saved['metadata']['request']!=descriptor:raise ValueError('Backtest ID belongs to different input/parameters')
        return saved
    data=freeze_receipts(source or database_path(),config) if bars is None else freeze_bars(bars,config)
    # Hash semantic input separately from retrieval/freeze timestamp metadata.
    payload={k:v for k,v in data.items() if k!='provenance'}
    metadata={'config':config,'request':descriptor,'provenance':data['provenance'],'kind':data['kind'],'dataset_sha256':digest(payload),
              'run_id':identity,'created_at':paper.now(),'assumptions':ASSUMPTIONS,'version':code_version()}
    path.parent.mkdir(parents=True,exist_ok=True)
    # Reserve the identity before initializing, preventing concurrent creation of two ledgers.
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    db=connect(path)
    try:
        paper.initialize(db)
        db.execute('CREATE TABLE backtest_run(id INTEGER PRIMARY KEY,metadata TEXT NOT NULL,frozen_input TEXT NOT NULL,status TEXT NOT NULL,result TEXT,error TEXT)')
        db.execute('INSERT INTO backtest_run VALUES(1,?,?,?,NULL,NULL)',(encoded(metadata),encoded(data),'running'));db.commit()
        result=evaluate(db,config,data)
        if reject_empty and not result['sample']['evaluation_completed_candles']:
            raise ValueError('No completed evaluation candles in this selection. Choose a populated regular-session range and timeframe.')
        result['chart']=chart_snapshot(db,config,data)
        db.execute("UPDATE backtest_run SET status='completed',result=? WHERE id=1",(encoded(result),));db.commit()
    except Exception as error:
        db.rollback();db.execute("UPDATE backtest_run SET status='failed',error=? WHERE id=1",(f'{type(error).__name__}: {error}',));db.commit();raise
    finally:db.close()
    return read(identity)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run_id');parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    parser.add_argument('--warmup-start');parser.add_argument('--timeframe',default='1m');parser.add_argument('--short',type=int,default=2);parser.add_argument('--long',type=int,default=3)
    parser.add_argument('--source');parser.add_argument('--bars');parser.add_argument('--output')
    args=parser.parse_args();request={'start':args.start,'end':args.end,'warmup_start':args.warmup_start or args.start,'timeframe':args.timeframe,'short':args.short,'long':args.long}
    result=run(args.run_id,request,source=args.source,bars=json.loads(Path(args.bars).read_text()) if args.bars else None)
    if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'run_id':result['run_id'],'status':result['status'],'metrics':{k:result['result'][k] for k in ('ending_equity','total_return','max_drawdown','sample')}},indent=2))


def list_runs():
    output=[]
    for path in sorted(root().glob('*.sqlite3'),key=lambda p:p.stat().st_mtime,reverse=True):
        saved=read(path.stem)
        output.append({k:saved[k] for k in ('run_id','metadata','status','error')})
    return output


def datasets():
    from datetime import timedelta
    recorded={'id':'recorded','label':'Recorded Yahoo observations','symbol':'AAPL','timeframes':list(TIMEFRAMES),
              'available':False,'count':0,'kind':'recorded_yahoo_receipts','provenance':'Original stored receipt/revision history; availability depends on capture'}
    source=database_path().resolve()
    if source.exists():
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute("SELECT d.receipt_time FROM deliveries d JOIN observations o USING(observation_id) WHERE o.source='yahoo' AND o.ticker='AAPL'").fetchall()
        if rows:
            stamps=[utc(r[0]) for r in rows]
            recorded.update(available=True,count=len(stamps),start=iso(min(stamps)),end=iso(max(stamps)+timedelta(microseconds=1)),warmup_start=iso(min(stamps)),default_timeframe='1m')
    items=[recorded]
    file=ROOT/'docs/evidence/aapl-2025-daily.json'
    if file.exists():
        doc=json.loads(file.read_text());dates=sorted(b['date'] for b in doc['bars'])
        if dates:
            items.append({'id':'aapl-2025-daily','label':'Yahoo historical daily bars · price-only','symbol':'AAPL','timeframes':['1d'],
                          'available':True,'count':len(dates),'kind':doc['kind'],'provenance':doc.get('source'),'retrieved_at':doc.get('retrieved_at'),
                          'warmup_start':dates[0]+'T00:00:00Z','start':dates[min(4,len(dates)-1)]+'T00:00:00Z',
                          'end':iso(utc(dates[-1]+'T00:00:00Z')+timedelta(days=1)),'default_timeframe':'1d'})
    return items
