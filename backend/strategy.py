"""Receipt-driven deterministic SMA simulation. No model calls or real orders."""
import re
import os
from backend import paper, pnl
from backend.candles import aggregate, utc
from backend.timeframes import resample, TIMEFRAMES
from backend.sma import sma, validate_windows


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sma_runs (
      id TEXT PRIMARY KEY, account_id TEXT NOT NULL UNIQUE REFERENCES paper_accounts(id),
      symbol TEXT NOT NULL, timeframe TEXT NOT NULL, short INTEGER NOT NULL, long INTEGER NOT NULL,
      enabled INTEGER NOT NULL, cursor INTEGER NOT NULL, clock TEXT NOT NULL,
      last_candle TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sma_events (
      id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES sma_runs(id), candle TEXT NOT NULL,
      receipt_id INTEGER NOT NULL REFERENCES deliveries(receipt_id), decision_time TEXT NOT NULL,
      short_value REAL, long_value REAL, signal TEXT, action TEXT NOT NULL, reason TEXT NOT NULL,
      cash_before INTEGER NOT NULL, shares_before INTEGER NOT NULL,
      order_id INTEGER REFERENCES paper_orders(id), UNIQUE(run_id,candle));
    ''')


def view(db, run, cutoff, clock):
    minutes=aggregate(db,run['symbol'],source='yahoo',as_of=clock,receipt_cutoff=cutoff)
    return resample(minutes['candles'],symbol=run['symbol'],timeframe=run['timeframe'],
                    as_of=clock,minute_status=minutes['status'])


def get(db, identity):
    row=db.execute('SELECT * FROM sma_runs WHERE id=?',(identity,)).fetchone()
    if row is None: raise ValueError('Unknown SMA strategy run')
    return dict(row)


def start(db, request):
    identity=request.get('run_id');short=request.get('short',2);long=request.get('long',3)
    validate_windows(short,long)
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}',identity):
        raise ValueError('Use a stable run ID of 1–64 letters, digits or hyphens')
    if request.get('symbol','AAPL')!='AAPL' or request.get('timeframe','1m') not in TIMEFRAMES:
        raise ValueError('Use AAPL and a supported timeframe')
    config={'symbol':'AAPL','timeframe':request.get('timeframe','1m'),'short':short,'long':long}
    db.execute('BEGIN IMMEDIATE')
    try:
        prior=db.execute('SELECT * FROM sma_runs WHERE id=?',(identity,)).fetchone()
        if prior:
            if any(prior[k]!=v for k,v in config.items()): raise ValueError('Run ID already has different configuration')
        else:
            rows=db.execute('SELECT receipt_id,receipt_time FROM deliveries ORDER BY receipt_id').fetchall()
            cursor=rows[-1]['receipt_id'] if rows else 0
            clock=max((utc(r['receipt_time']) for r in rows),default=utc(paper.now())).isoformat()
            initial=view(db,config,cursor,clock)
            completed=[c['timestamp'] for c in initial['candles'] if initial['status'][c['timestamp']]['complete']]
            account_id='strategy-'+identity
            db.execute('INSERT INTO paper_accounts VALUES(?,?,?,?,?,?,?,?)',
                       (account_id,'strategy',100000,100000,paper.now(),cursor,0,None))
            db.execute('INSERT INTO sma_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (identity,account_id,'AAPL',config['timeframe'],short,long,1,cursor,clock,max(completed,default=''),paper.now()))
        db.commit()
    except Exception:db.rollback();raise
    return state(db,identity)


def process_locked(db):
    """Called inside paper.process_live transaction; never consumes future receipts."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sma_runs'").fetchone(): return
    for initial in db.execute('SELECT * FROM sma_runs WHERE enabled=1').fetchall():
        run=dict(initial)
        receipts=db.execute('''SELECT d.*,o.ticker,o.source FROM deliveries d JOIN observations o USING(observation_id)
                               WHERE receipt_id>? ORDER BY receipt_id''',(run['cursor'],)).fetchall()
        for row in receipts:
            clock=max(utc(run['clock']),utc(row['receipt_time'])).isoformat()
            acct=paper.account(db,run['account_id'])
            pnl.completed_candles(db,acct['id'],as_of=clock,receipt_cutoff=row['receipt_id']-1)
            paper._fill_receipt(db,acct,row)
            pnl.completed_candles(db,acct['id'],as_of=clock,receipt_cutoff=row['receipt_id'])
            # Submission boundary is this revealed receipt, never the database's final maximum.
            db.execute('UPDATE paper_accounts SET cursor=? WHERE id=?',(row['receipt_id'],acct['id']))
            current=view(db,run,row['receipt_id'],clock)
            values=sma(current['candles'],current['status'],run['short'],run['long'])['values']
            candles={c['timestamp']:c for c in current['candles']}
            for value in values:
                stamp=value['timestamp']
                if stamp<=run['last_candle'] or not current['status'][stamp]['complete']:continue
                cash=paper.account(db,acct['id'])['cash_cents']; held=paper.shares(db,acct['id'],'AAPL')
                pending=db.execute("SELECT 1 FROM paper_orders WHERE account_id=? AND status='pending'",(acct['id'],)).fetchone()
                action,reason=choose_action(value,cash,held,bool(pending),candles[stamp]['close'])
                order=None
                if action!='none':
                    order=paper.execute(db,request_id=f'sma:{run["id"]}:{stamp}',action=action,
                                        quantity=1 if action=='buy' else None,account_id=acct['id'],_in_transaction=True)
                    db.execute('UPDATE paper_orders SET submitted_at=? WHERE id=?',(clock,order['id']))
                db.execute('INSERT INTO sma_events(run_id,candle,receipt_id,decision_time,short_value,long_value,signal,action,reason,cash_before,shares_before,order_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (run['id'],stamp,row['receipt_id'],clock,value['short'],value['long'],value['signal'],action,reason,cash,held,order['id'] if order else None))
                run['last_candle']=stamp
            run.update(cursor=row['receipt_id'],clock=clock)
            db.execute('UPDATE sma_runs SET cursor=?,clock=?,last_candle=? WHERE id=?',
                       (run['cursor'],clock,run['last_candle'],run['id']))


def stop(db,identity):
    db.execute('BEGIN IMMEDIATE')
    try:
        run=get(db,identity)
        db.execute('UPDATE sma_runs SET enabled=0 WHERE id=?',(identity,))
        db.execute("UPDATE paper_orders SET status='rejected',rejection_reason='Strategy stopped before fill' WHERE account_id=? AND status='pending'",(run['account_id'],))
        db.commit()
    except Exception:db.rollback();raise
    return state(db,identity)


def state(db,identity):
    run=get(db,identity)
    events=[dict(r) for r in db.execute('''SELECT e.*,o.status AS order_status,o.rejection_reason,
        f.id AS fill_id,f.receipt_id AS fill_receipt,f.price_cents AS fill_price_cents,
        f.executed_at AS fill_time FROM sma_events e LEFT JOIN paper_orders o ON o.id=e.order_id
        LEFT JOIN paper_fills f ON f.order_id=o.id WHERE e.run_id=? ORDER BY e.id''',(identity,))]
    return {'run':run,'events':events,'account':paper.snapshot(db,run['account_id']),
            'data_label':os.environ.get('MARKET_DATA_LABEL','')}


def choose_action(value, cash, held, pending, close):
    """Shared forward/backtest policy; exact crossover already computed by Python."""
    price=paper.price_cents(close)
    if value['short'] is None or value['long'] is None:return 'none','SMA warm-up'
    if pending:return 'none','Order already pending'
    if value['signal']=='up':
        if held:return 'none','Already holding; no pyramiding'
        if price is None:return 'none','Signal price unavailable'
        if cash<price:return 'none','Insufficient cash at signal'
        return 'buy','Upward crossover: buy one share'
    if value['signal']=='down':
        return ('close','Downward crossover: close position') if held else ('none','Flat; no position to close')
    return 'none','No crossover'
