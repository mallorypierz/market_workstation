"""Local-only long-only simulator. No broker or real-money integration."""
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from backend.recorder import connect
from backend.candles import utc
from backend import pnl


def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS paper_accounts (
      id TEXT PRIMARY KEY, mode TEXT NOT NULL, cash_cents INTEGER NOT NULL CHECK(cash_cents>=0),
      starting_cash_cents INTEGER NOT NULL, created_at TEXT NOT NULL,
      cursor INTEGER NOT NULL DEFAULT 0, replay_step INTEGER NOT NULL DEFAULT 0, spec_json TEXT);
    CREATE TABLE IF NOT EXISTS paper_positions (
      account_id TEXT NOT NULL REFERENCES paper_accounts(id), symbol TEXT NOT NULL,
      quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(account_id,symbol));
    CREATE TABLE IF NOT EXISTS paper_orders (
      id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES paper_accounts(id),
      request_id TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL, action TEXT NOT NULL,
      side TEXT NOT NULL, quantity INTEGER, requested_quantity_json TEXT NOT NULL,
      submitted_at TEXT NOT NULL, after_receipt INTEGER NOT NULL,
      status TEXT NOT NULL, rejection_reason TEXT);
    CREATE TABLE IF NOT EXISTS paper_fills (
      id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES paper_orders(id),
      observation_id INTEGER NOT NULL REFERENCES observations(observation_id),
      receipt_id INTEGER NOT NULL REFERENCES deliveries(receipt_id),
      price_cents INTEGER NOT NULL CHECK(price_cents>0), quantity INTEGER NOT NULL CHECK(quantity>0),
      fee_cents INTEGER NOT NULL DEFAULT 0, executed_at TEXT NOT NULL, processed_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS paper_requests (
      request_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
      order_id INTEGER REFERENCES paper_orders(id), response_json TEXT NOT NULL);
    ''')
    maximum=db.execute('SELECT COALESCE(MAX(receipt_id),0) FROM deliveries').fetchone()[0]
    db.execute("INSERT OR IGNORE INTO paper_accounts(id,mode,cash_cents,starting_cash_cents,created_at,cursor) VALUES('live','live',100000,100000,?,?)",(now(),maximum))
    db.commit()
    pnl.initialize(db)


def open_account_db():
    db=connect(); initialize(db); return db


def shares(db, account_id, symbol):
    row=db.execute('SELECT quantity FROM paper_positions WHERE account_id=? AND symbol=?',(account_id,symbol)).fetchone()
    return row[0] if row else 0


def account(db, account_id):
    row=db.execute('SELECT * FROM paper_accounts WHERE id=?',(account_id,)).fetchone()
    if row is None: raise ValueError('Unknown paper account')
    return row


def price_cents(value):
    try:
        value=Decimal(str(value))
        if not value.is_finite() or value<=0: return None
        cents=int((value*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        return cents if 0<cents<=10**12 else None
    except (InvalidOperation,ValueError,OverflowError): return None


def selected_receipts(db, spec):
    start,end=utc(spec['start']),utc(spec['end'])
    rows=db.execute('''SELECT d.*,o.ticker,o.source FROM deliveries d JOIN observations o USING(observation_id)
      WHERE o.source='yahoo' AND o.ticker=? AND d.receipt_id<=? ORDER BY d.receipt_id''',(spec['symbol'],spec['snapshot_cutoff'])).fetchall()
    return [row for row in rows if start<=utc(row['receipt_time'])<end]


def _fill_receipt(db, acct, row):
    # Exact repeat deliveries and explicitly identified corrections are not new executable quotes.
    first=db.execute('SELECT MIN(receipt_id) FROM deliveries WHERE observation_id=?',(row['observation_id'],)).fetchone()[0]
    if row['receipt_id']!=first or db.execute('SELECT 1 FROM revisions WHERE identified_at_receipt_id=?',(row['receipt_id'],)).fetchone(): return
    if row['source']!='yahoo': return
    payload=json.loads(row['decoded_message_json']); cents=price_cents(payload.get('price'))
    if cents is None: return
    pending=db.execute("SELECT * FROM paper_orders WHERE account_id=? AND symbol=? AND status='pending' AND after_receipt<? ORDER BY id",(acct['id'],row['ticker'],row['receipt_id'])).fetchall()
    for order in pending:
        cash=account(db,acct['id'])['cash_cents']; held=shares(db,acct['id'],row['ticker'])
        quantity=held if order['action']=='close' else order['quantity']
        reason=None
        if 'decision_id' in order.keys() and order['decision_id']:
            from backend import automation
            reason=automation.fill_guard(db,order,row)
        if reason: pass
        elif quantity is None or quantity<=0: reason='No shares to close'
        elif order['side']=='sell' and quantity>held: reason='Insufficient shares at fill'
        elif order['side']=='buy' and quantity*cents>cash: reason='Insufficient cash at fill'
        elif order['side']=='sell' and cash+quantity*cents>2**63-1: reason='Account balance exceeds storage limit'
        if reason:
            db.execute("UPDATE paper_orders SET status='rejected',rejection_reason=? WHERE id=?",(reason,order['id']))
            if 'decision_id' in order.keys() and order['decision_id']:
                automation.fill_result(db,order,reason=reason)
            continue
        delta=quantity if order['side']=='buy' else -quantity
        db.execute('UPDATE paper_accounts SET cash_cents=? WHERE id=?',(cash-delta*cents,acct['id']))
        db.execute('INSERT INTO paper_positions(account_id,symbol,quantity) VALUES(?,?,?) ON CONFLICT(account_id,symbol) DO UPDATE SET quantity=excluded.quantity',(acct['id'],row['ticker'],held+delta))
        fill_id=db.execute('INSERT INTO paper_fills(order_id,observation_id,receipt_id,price_cents,quantity,executed_at,processed_at) VALUES(?,?,?,?,?,?,?)',
                   (order['id'],row['observation_id'],row['receipt_id'],cents,quantity,row['receipt_time'],now())).lastrowid
        pnl.record_fill(db,fill_id)
        if 'decision_id' in order.keys() and order['decision_id']:automation.fill_result(db,order,fill_id=fill_id)
        db.execute("UPDATE paper_orders SET status='filled',quantity=? WHERE id=?",(quantity,order['id']))


def _advance_account(db, account_id):
    acct=account(db,account_id)
    rows=db.execute('SELECT d.*,o.ticker,o.source FROM deliveries d JOIN observations o USING(observation_id) WHERE receipt_id>? ORDER BY receipt_id',(acct['cursor'],)).fetchall()
    for row in rows:
        pnl.completed_candles(db,account_id,as_of=row['receipt_time'],receipt_cutoff=row['receipt_id']-1)
        _fill_receipt(db,acct,row)
        pnl.completed_candles(db,account_id,as_of=row['receipt_time'],receipt_cutoff=row['receipt_id'])
        db.execute("UPDATE paper_accounts SET cursor=? WHERE id=?",(row['receipt_id'],account_id))
    pnl.completed_candles(db,account_id,as_of=now(),receipt_cutoff=account(db,account_id)['cursor'])


def _advance_live(db):
    for row in db.execute("SELECT id FROM paper_accounts WHERE mode IN ('live','test')").fetchall():
        _advance_account(db,row['id'])


def process_live(db):
    # Callback can be used before paper accounts have been initialized.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_accounts'").fetchone(): return
    db.execute('BEGIN IMMEDIATE')
    try: _advance_live(db); db.commit()
    except Exception: db.rollback(); raise


def snapshot(db, account_id='live'):
    acct=dict(account(db,account_id))
    return {**acct,'cash':acct['cash_cents']/100,'pnl_history':pnl.history(db,account_id),'pnl_current':pnl.current(db,account_id),
      'positions':[dict(r) for r in db.execute('SELECT symbol,quantity FROM paper_positions WHERE account_id=? ORDER BY symbol',(account_id,))],
      'orders':[dict(r) for r in db.execute('SELECT * FROM paper_orders WHERE account_id=? ORDER BY id',(account_id,))],
      'fills':[dict(r) for r in db.execute('''SELECT f.*,o.symbol,o.side FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id WHERE o.account_id=? ORDER BY f.id''',(account_id,))]}


def execute(db, *, request_id, action, symbol='AAPL', quantity=None, account_id='live', _in_transaction=False):
    """Reusable order/hold/wait entry point; stable request ID is mandatory."""
    if not isinstance(request_id,str) or not 1<=len(request_id)<=128: raise ValueError('A stable request ID of 1–128 characters is required')
    if action not in {'buy','sell','close','hold','wait'}: raise ValueError('Unknown paper action')
    if symbol!='AAPL': raise ValueError('Paper execution currently supports AAPL only')
    payload=json.dumps({'account_id':account_id,'action':action,'symbol':symbol,'quantity':quantity},sort_keys=True,allow_nan=False)
    if not _in_transaction: db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT * FROM paper_requests WHERE request_id=?',(request_id,)).fetchone()
        if previous:
            if previous['payload_json']!=payload: raise ValueError('Request ID was already used with different parameters')
            result=dict(db.execute('SELECT * FROM paper_orders WHERE id=?',(previous['order_id'],)).fetchone()) if previous['order_id'] else json.loads(previous['response_json'])
            if not _in_transaction: db.commit()
            return result
        acct=account(db,account_id)
        if acct['mode'] in ('live','test') and not _in_transaction: _advance_live(db); acct=account(db,account_id)
        held=shares(db,account_id,symbol)
        submitted=now()
        if acct['mode']=='replay':
            spec=json.loads(acct['spec_json']); rows=selected_receipts(db,spec)
            submitted=rows[acct['replay_step']-1]['receipt_time'] if acct['replay_step'] else spec['start']
        if action in {'hold','wait'}:
            reason='Hold requires a position' if action=='hold' and held==0 else 'Wait requires cash-only state' if action=='wait' and held else None
            result={'action':action,'status':'rejected' if reason else 'no_order','rejection_reason':reason,'request_id':request_id}
            order_id=None
        else:
            reason=None
            valid=type(quantity) is int and 0<quantity<=2**31-1
            qty=held if action=='close' else quantity if valid else None
            if action in {'buy','sell'} and not valid: reason='Quantity must be a positive whole number (maximum 2147483647)'
            elif action=='close' and quantity is not None: reason='Close takes no quantity; it sells the whole position at fill'
            elif action in {'sell','close'} and (qty is None or qty<=0 or qty>held): reason='Insufficient shares'
            boundary=db.execute('SELECT COALESCE(MAX(receipt_id),0) FROM deliveries').fetchone()[0] if acct['mode'] in ('live','test') else acct['cursor']
            order_id=db.execute('''INSERT INTO paper_orders(account_id,request_id,symbol,action,side,quantity,requested_quantity_json,submitted_at,after_receipt,status,rejection_reason)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(account_id,request_id,symbol,action,'buy' if action=='buy' else 'sell',qty,json.dumps(quantity),submitted,boundary,'rejected' if reason else 'pending',reason)).lastrowid
            result=dict(db.execute('SELECT * FROM paper_orders WHERE id=?',(order_id,)).fetchone())
        db.execute('INSERT INTO paper_requests VALUES(?,?,?,?)',(request_id,payload,order_id,json.dumps(result)))
        if not _in_transaction: db.commit()
        return result
    except Exception:
        if not _in_transaction: db.rollback()
        raise


def start_replay(db, *, account_id, symbol, start, end, snapshot_cutoff, step=0):
    if not account_id.startswith('replay-') or len(account_id)>128: raise ValueError('Replay account ID must start with replay-')
    if symbol!='AAPL' or utc(start)>=utc(end) or type(step) is not int or step<0 or type(snapshot_cutoff) is not int or snapshot_cutoff<0: raise ValueError('Invalid replay selection')
    spec={'symbol':symbol,'start':start,'end':end,'snapshot_cutoff':snapshot_cutoff,'initial_step':step}
    encoded=json.dumps(spec,sort_keys=True)
    db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT * FROM paper_accounts WHERE id=?',(account_id,)).fetchone()
        if previous:
            if previous['spec_json']!=encoded: raise ValueError('Replay ID belongs to a different selection')
        else:
            rows=selected_receipts(db,spec)
            if step>len(rows): raise ValueError('Replay step exceeds selection')
            cursor=rows[step-1]['receipt_id'] if step else 0
            db.execute('INSERT INTO paper_accounts VALUES(?,?,?,?,?,?,?,?)',(account_id,'replay',100000,100000,now(),cursor,step,encoded))
        db.commit(); return snapshot(db,account_id)
    except Exception: db.rollback(); raise


def advance_replay(db, account_id, step):
    db.execute('BEGIN IMMEDIATE')
    try:
        acct=account(db,account_id)
        if acct['mode']!='replay': raise ValueError('Not a replay paper account')
        rows=selected_receipts(db,json.loads(acct['spec_json']))
        if type(step) is not int or not acct['replay_step']<=step<=len(rows): raise ValueError('Paper replay cannot rewind; start a new replay paper account')
        for index in range(acct['replay_step'],step):
            row=rows[index]
            clock_time=max(utc(r['receipt_time']) for r in rows[:index+1])
            pnl.completed_candles(db,account_id,as_of=clock_time,receipt_cutoff=row['receipt_id']-1,receipt_ids=[r['receipt_id'] for r in rows[:index]])
            _fill_receipt(db,acct,row)
            pnl.completed_candles(db,account_id,as_of=clock_time,receipt_cutoff=row['receipt_id'],receipt_ids=[r['receipt_id'] for r in rows[:index+1]])
        cursor=rows[step-1]['receipt_id'] if step else 0
        db.execute('UPDATE paper_accounts SET replay_step=?,cursor=? WHERE id=?',(step,cursor,account_id))
        db.commit();return snapshot(db,account_id)
    except Exception: db.rollback(); raise


def configured_order_size():
    """Server default for decision proposals; manual controls retain explicit quantities."""
    value = os.environ.get('MARKET_PAPER_ORDER_SIZE', '1')
    if not value.isascii() or not value.isdecimal() or not 0 < int(value) <= 2**31-1:
        raise ValueError('MARKET_PAPER_ORDER_SIZE must be a positive whole number up to 2147483647')
    return int(value)
