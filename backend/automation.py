"""Persisted paper automation claims, Stop fences, and simulator execution guards."""
from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import uuid
from backend import paper,decisions,decision_review
from backend.candles import utc
from backend.recorder import database_path
from backend.timeframes import history_view
from backend.sma import validate_windows


def initialize(db):
    decisions.initialize(db)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS automation_controls (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL, strategy TEXT NOT NULL, symbol TEXT NOT NULL,
        interval TEXT NOT NULL, short INTEGER NOT NULL, long INTEGER NOT NULL, enabled INTEGER NOT NULL,
        generation INTEGER NOT NULL, after_candle TEXT NOT NULL,
        UNIQUE(account_id,strategy,symbol,interval));
      CREATE TABLE IF NOT EXISTS automation_jobs (
        id TEXT PRIMARY KEY, control_id TEXT NOT NULL REFERENCES automation_controls(id), generation INTEGER NOT NULL,
        account_id TEXT NOT NULL, strategy TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL,
        candle TEXT NOT NULL, snapshot_id TEXT, decision_id TEXT UNIQUE, status TEXT NOT NULL, reason TEXT,
        order_id INTEGER, fill_id INTEGER, created_at TEXT NOT NULL, expires_at TEXT, result_json TEXT,
        UNIQUE(account_id,strategy,symbol,interval,candle));
    ''')
    for table in ('paper_orders','paper_fills','paper_pnl'):
        if 'decision_id' not in {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}:
            db.execute('ALTER TABLE '+table+' ADD COLUMN decision_id TEXT')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS automated_order_decision ON paper_orders(decision_id) WHERE decision_id IS NOT NULL')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS automated_fill_decision ON paper_fills(decision_id) WHERE decision_id IS NOT NULL')
    db.commit()


def test_database():
    path=database_path().resolve()
    roots=[Path(tempfile.gettempdir()).resolve(),Path('/private/tmp').resolve()]
    return os.environ.get('MARKET_AUTOMATION_TEST')=='1' and any(path.is_relative_to(r) for r in roots)


def max_age():
    value=int(os.environ.get('MARKET_DECISION_MAX_AGE_SECONDS','120'))
    if not 1<=value<=3600:raise ValueError('Decision maximum age must be 1–3600 seconds')
    return value


def control(db,identity):
    row=db.execute('SELECT * FROM automation_controls WHERE id=?',(identity,)).fetchone()
    if row is None:raise ValueError('Unknown automation control')
    return dict(row)


def job(db,identity):
    row=db.execute('SELECT * FROM automation_jobs WHERE id=?',(identity,)).fetchone()
    if row is None:raise ValueError('Unknown automation job')
    return dict(row)


def cancel_locked(db,identity,reason):
    db.execute('UPDATE automation_controls SET enabled=0,generation=generation+1 WHERE id=?',(identity,))
    db.execute("UPDATE paper_orders SET status='rejected',rejection_reason=? WHERE status='pending' AND id IN (SELECT order_id FROM automation_jobs WHERE control_id=?)",(reason,identity))
    db.execute("UPDATE automation_jobs SET status='skipped',reason=? WHERE control_id=? AND status IN ('reserved','awaiting_image','analyzing','pending')",(reason,identity))


def stop(db,identity,reason='Automation stopped'):
    db.execute('BEGIN IMMEDIATE')
    try:cancel_locked(db,identity,reason);db.commit()
    except Exception:db.rollback();raise
    return state(db,identity)


def startup(db):
    initialize(db)
    db.execute('BEGIN IMMEDIATE')
    try:
        for row in db.execute('SELECT id FROM automation_controls').fetchall():cancel_locked(db,row['id'],'Backend restarted; Start required')
        db.commit()
    except Exception:db.rollback();raise


def start(db,request):
    symbol=request.get('symbol','AAPL');interval=request.get('interval','1m');short=request.get('short',2);long=request.get('long',3)
    if symbol!='AAPL':raise ValueError('Automation supports AAPL only')
    validate_windows(short,long);max_age()
    account_id='automation-test' if test_database() else request.get('account_id','live')
    if test_database():
        maximum=db.execute('SELECT COALESCE(MAX(receipt_id),0) FROM deliveries').fetchone()[0]
        db.execute("INSERT OR IGNORE INTO paper_accounts(id,mode,cash_cents,starting_cash_cents,created_at,cursor) VALUES(?,'test',100000,100000,?,?)",(account_id,paper.now(),maximum));db.commit()
    acct=paper.account(db,account_id)
    if acct['mode'] not in ('live','test'):raise ValueError('Automation uses forward live/fixture arrivals; replay execution is manual')
    if acct['mode']=='test' and not test_database():raise ValueError('Test automation requires a disposable test database')
    view=history_view(symbol=symbol,timeframe=interval,source='yahoo',as_of=paper.now())
    completed=[c['timestamp'] for c in view['candles'] if view['status'][c['timestamp']]['complete']]
    after=max(completed) if completed else paper.now()
    strategy=f'sma-cross-v1:{short}:{long}'
    db.execute('BEGIN IMMEDIATE')
    try:
        old=db.execute('SELECT * FROM automation_controls WHERE account_id=? AND strategy=? AND symbol=? AND interval=?',(account_id,strategy,symbol,interval)).fetchone()
        if old:
            identity=old['id']
            if not old['enabled']:db.execute('UPDATE automation_controls SET enabled=1,generation=generation+1,after_candle=? WHERE id=?',(after,identity))
        else:
            identity=str(uuid.uuid4());db.execute('INSERT INTO automation_controls VALUES(?,?,?,?,?,?,?,?,?,?)',(identity,account_id,strategy,symbol,interval,short,long,1,1,after))
        db.commit()
    except Exception:db.rollback();raise
    return state(db,identity)


def state(db,identity):
    c=control(db,identity)
    jobs=[]
    for row in db.execute('SELECT * FROM automation_jobs WHERE control_id=? ORDER BY candle DESC',(identity,)):
        r=dict(row);r['decision']=decisions.get_decision(db,r['decision_id']) if r['decision_id'] else None
        r['snapshot']=decisions.get_snapshot(db,r['snapshot_id']) if r['snapshot_id'] else None
        r['execution']=json.loads(r['result_json']) if r['result_json'] else None
        jobs.append(r)
    return {'control':c,'jobs':jobs,'account':paper.snapshot(db,c['account_id']),'test_account':c['account_id']=='automation-test'}


def reserve(db,identity,request):
    c=control(db,identity);stamp=utc(request.get('candle_timestamp')).isoformat().replace('+00:00','Z');ending=decisions.candle_end(stamp,c['interval'])
    if utc(stamp)<=utc(c['after_candle']):raise ValueError('Only candles completed after Start are scheduled')
    if ending>utc(paper.now()):raise ValueError('Candle is still forming')
    db.execute('BEGIN IMMEDIATE')
    try:
        c=control(db,identity)
        old=db.execute('SELECT id FROM automation_jobs WHERE account_id=? AND strategy=? AND symbol=? AND interval=? AND candle=?',(c['account_id'],c['strategy'],c['symbol'],c['interval'],stamp)).fetchone()
        if old:db.commit();return job(db,old['id'])
        if not c['enabled'] or request.get('generation')!=c['generation']:raise ValueError('Automation was stopped or restarted')
        jid=str(uuid.uuid4());expires=(ending+timedelta(seconds=max_age())).isoformat()
        stale=utc(paper.now())>utc(expires)
        db.execute('INSERT INTO automation_jobs(id,control_id,generation,account_id,strategy,symbol,interval,candle,status,reason,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (jid,identity,c['generation'],c['account_id'],c['strategy'],c['symbol'],c['interval'],stamp,'skipped' if stale else 'reserved','Decision window already expired' if stale else None,paper.now(),expires));db.commit()
    except Exception:db.rollback();raise
    if stale:return job(db,jid)
    snapshot=decisions.create_snapshot(db,{'symbol':c['symbol'],'interval':c['interval'],'short':c['short'],'long':c['long'],'account_id':c['account_id'],'candle_timestamp':stamp})
    db.execute("UPDATE automation_jobs SET snapshot_id=?,status=CASE WHEN status='reserved' THEN 'awaiting_image' ELSE status END WHERE id=?",(snapshot['snapshot_id'],jid));db.commit()
    return {**job(db,jid),'snapshot':snapshot}


def submit(db,jid,request,provider=None):
    db.execute('BEGIN IMMEDIATE')
    try:
        j=job(db,jid);c=control(db,j['control_id'])
        if j['status']!='awaiting_image':db.commit();return j
        if not c['enabled'] or c['generation']!=j['generation']:
            db.execute("UPDATE automation_jobs SET status='skipped',reason='Automation stopped' WHERE id=?",(jid,));db.commit();return job(db,jid)
        db.execute("UPDATE automation_jobs SET status='analyzing' WHERE id=?",(jid,));db.commit()
    except Exception:db.rollback();raise
    s=decisions.get_snapshot(db,j['snapshot_id'])
    # Caller supplies only image bytes; identity/range always come from the reserved snapshot.
    result=decision_review.run(db,{'analysis':'chart','snapshot_id':j['snapshot_id'],'snapshot_sha256':s['sha256'],'chart_range':s.get('capture_range'),'image':request.get('image')},provider)
    db.execute('UPDATE automation_jobs SET decision_id=? WHERE id=?',(result['decision_id'],jid));db.commit()
    return apply(db,jid)


def gate(db,j,at=None):
    c=control(db,j['control_id'])
    if not c['enabled'] or c['generation']!=j['generation']:return 'Automation stopped or generation changed'
    if utc(at or paper.now())>utc(j['expires_at']) or utc(paper.now())>utc(j['expires_at']):return 'Decision expired before execution'
    s=decisions.get_snapshot(db,j['snapshot_id']);r=decisions.get_decision(db,j['decision_id']) if j['decision_id'] else None
    if not s or not r:return 'Decision or snapshot missing'
    if s.get('symbol')!=j['symbol'] or s.get('interval')!=j['interval'] or s.get('candle_timestamp')!=j['candle'] or s.get('account',{}).get('account_id')!=j['account_id'] or r['snapshot_id']!=s['snapshot_id']:return 'Account, symbol or candle mismatch'
    if not s['complete'] or r['status']!='valid' or not r.get('final_check',{}).get('passed') or r.get('roles',{}).get('reviewer',{}).get('verdict')!='accept':return 'Review veto or failed Python validation'
    if not r.get('image'):return 'Fresh frozen chart image required'
    for role in r.get('roles',{}).values():
        if role.get('snapshot_sha256')!=s['sha256'] or role.get('image_sha256')!=r['image']['sha256']:return 'Role evidence mismatch'
    if s['kind']=='test':
        if not test_database() or j['account_id']!='automation-test':return 'Test snapshot may only execute in disposable automation-test account'
    elif not s['order_eligible']:return 'Snapshot is execution-ineligible'
    check=decision_review.checks(s,r)
    if not all(check[k] for k in ('account_rules_pass','strategy_rules_pass','chart_evidence_pass')):return 'Recomputed Python validation failed'
    if utc(at or paper.now())<utc(s['decision_time']):return 'Execution predates decision'
    return None


def apply(db,jid):
    db.execute('BEGIN IMMEDIATE')
    try:
        j=job(db,jid)
        if j['status'] in ('filled','pending','no_order','skipped'):db.commit();return j
        reason=gate(db,j)
        if reason:
            db.execute("UPDATE automation_jobs SET status='skipped',reason=? WHERE id=?",(reason,jid));db.commit();return job(db,jid)
        r=decisions.get_decision(db,j['decision_id']);s=decisions.get_snapshot(db,j['snapshot_id']);action=r['proposal']['action']
        if r['proposal'].get('quantity')!=(s['order_size'] if action in ('buy','sell') else s['account']['shares'] if action=='close' else None):raise ValueError('Proposal size does not match frozen configuration')
        order=paper.execute(db,request_id='automation:'+jid,action=action,symbol=j['symbol'],account_id=j['account_id'],quantity=s['order_size'] if action in ('buy','sell') else None,_in_transaction=True)
        if order.get('id'):
            db.execute('UPDATE paper_orders SET decision_id=? WHERE id=?',(j['decision_id'],order['id']))
            db.execute('UPDATE automation_jobs SET order_id=?,status=?,reason=? WHERE id=?',(order['id'],'pending' if order['status']=='pending' else 'skipped',order.get('rejection_reason'),jid))
        else:db.execute('UPDATE automation_jobs SET status=?,reason=? WHERE id=?',('no_order' if order['status']=='no_order' else 'skipped',order.get('rejection_reason'),jid))
        db.commit();return job(db,jid)
    except Exception:db.rollback();raise


def fill_guard(db,order,receipt):
    jrow=db.execute('SELECT * FROM automation_jobs WHERE decision_id=?',(order['decision_id'],)).fetchone()
    if not jrow:return 'Automation decision has no claimed candle'
    j=dict(jrow)
    if j['status']!='pending' or j['order_id']!=order['id'] or j['account_id']!=order['account_id']:return 'Decision already handled or order mismatch'
    if db.execute('SELECT 1 FROM paper_fills WHERE decision_id=?',(order['decision_id'],)).fetchone():return 'Decision already filled'
    return gate(db,j,receipt['receipt_time'])


def fill_result(db,order,fill_id=None,reason=None):
    if 'decision_id' not in order.keys() or not order['decision_id']:return
    if fill_id:
        db.execute('UPDATE paper_fills SET decision_id=? WHERE id=?',(order['decision_id'],fill_id))
        db.execute('UPDATE paper_pnl SET decision_id=? WHERE fill_id=?',(order['decision_id'],fill_id))
    result={'cash_cents':paper.account(db,order['account_id'])['cash_cents'],'shares':paper.shares(db,order['account_id'],order['symbol']),
            'fill_id':fill_id,'decision_id':order['decision_id'],'reason':reason}
    db.execute('UPDATE automation_jobs SET status=?,reason=?,fill_id=?,result_json=? WHERE decision_id=?',('filled' if fill_id else 'skipped',reason,fill_id,json.dumps(result),order['decision_id']))
