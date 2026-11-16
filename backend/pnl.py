"""Append-only paper P&L in exact fractional cents; values exposed in dollars."""
from datetime import datetime, timezone
from fractions import Fraction
import json

from backend.candles import aggregate, utc
from backend.timeframes import resample


def iso(value): return utc(value).isoformat().replace('+00:00','Z')
def clock(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def dollars(value): return None if value is None else float(value / 100)


def initialize(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS paper_pnl (
      id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES paper_accounts(id), symbol TEXT NOT NULL,
      event_key TEXT NOT NULL, event_type TEXT NOT NULL, event_time TEXT NOT NULL, recorded_at TEXT NOT NULL,
      fill_id INTEGER REFERENCES paper_fills(id), observation_id INTEGER REFERENCES observations(observation_id),
      candle_timestamp TEXT, candle_end TEXT, knowledge_receipt INTEGER,
      price_time TEXT, price_source TEXT NOT NULL, price_exact TEXT, valuation_status TEXT NOT NULL,
      cash_cents INTEGER NOT NULL, quantity INTEGER NOT NULL, average_cost_exact TEXT,
      realized_exact TEXT NOT NULL, unrealized_exact TEXT, total_exact TEXT,
      price REAL, average_cost REAL, realized REAL NOT NULL, unrealized REAL, total REAL,
      UNIQUE(account_id,symbol,event_key));
      CREATE INDEX IF NOT EXISTS paper_pnl_account ON paper_pnl(account_id,id);''')
    # Old fills can be reconstructed exactly; old valuation history cannot be invented.
    db.execute('BEGIN IMMEDIATE')
    try:
        for row in db.execute('SELECT id FROM paper_fills ORDER BY id').fetchall(): record_fill(db,row['id'])
        db.commit()
    except Exception: db.rollback(); raise


def ledger(db, account_id, symbol, through_fill=None):
    cash=db.execute('SELECT starting_cash_cents FROM paper_accounts WHERE id=?',(account_id,)).fetchone()[0]
    quantity=0; average=Fraction(0); realized=Fraction(0)
    rows=db.execute('''SELECT f.*,o.side,o.symbol FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id
      WHERE o.account_id=? AND (? IS NULL OR f.id<=?) ORDER BY f.id''',(account_id,through_fill,through_fill)).fetchall()
    for row in rows:
        q=row['quantity'];price=Fraction(row['price_cents'])
        cash += (-1 if row['side']=='buy' else 1)*q*row['price_cents'] - row['fee_cents']
        if row['symbol']!=symbol: continue
        if row['side']=='buy':
            average=(quantity*average+q*price)/(quantity+q); quantity+=q
        else:
            realized+=q*(price-average);quantity-=q
            if quantity==0: average=Fraction(0)
    return cash,quantity,average,realized


def append(db, *, account_id, symbol, key, kind, event_time, price, price_time, price_source,
           fill_id=None, observation_id=None, candle_timestamp=None, candle_end=None, knowledge_receipt=None):
    if db.execute('SELECT 1 FROM paper_pnl WHERE account_id=? AND symbol=? AND event_key=?',(account_id,symbol,key)).fetchone(): return
    cash,q,average,realized=ledger(db,account_id,symbol,fill_id)
    # Prices must be finite positive rationals; unavailable is never replaced by zero.
    try: mark=Fraction(str(price)) if price is not None else None
    except (ValueError,ZeroDivisionError): mark=None
    if mark is not None and mark<=0: mark=None
    unrealized=Fraction(0) if q==0 else q*(mark-average) if mark is not None else None
    total=None if unrealized is None else realized+unrealized
    status='closed' if q==0 else 'available' if mark is not None else 'unavailable'
    db.execute('''INSERT INTO paper_pnl(account_id,symbol,event_key,event_type,event_time,recorded_at,
      fill_id,observation_id,candle_timestamp,candle_end,knowledge_receipt,price_time,price_source,price_exact,valuation_status,
      cash_cents,quantity,average_cost_exact,realized_exact,unrealized_exact,total_exact,price,average_cost,realized,unrealized,total)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (account_id,symbol,key,kind,iso(event_time),clock(),fill_id,observation_id,candle_timestamp,candle_end,knowledge_receipt,
       price_time,price_source,None if mark is None else str(mark),status,cash,q,str(average) if q else None,
       str(realized),None if unrealized is None else str(unrealized),None if total is None else str(total),
       dollars(mark),dollars(average) if q else None,dollars(realized),dollars(unrealized),dollars(total)))


def record_fill(db, fill_id):
    row=db.execute('''SELECT f.*,o.account_id,o.symbol,o.side,o.action,obs.source,obs.source_time_ms
      FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id JOIN observations obs USING(observation_id)
      WHERE f.id=?''',(fill_id,)).fetchone()
    stamp=None
    try: stamp=datetime.fromtimestamp(row['source_time_ms']/1000,timezone.utc).isoformat().replace('+00:00','Z')
    except (TypeError,ValueError,OSError,OverflowError): pass
    append(db,account_id=row['account_id'],symbol=row['symbol'],key=f'fill:{fill_id}',kind=f"{row['action']} fill",
           event_time=row['executed_at'],price=row['price_cents'],price_time=stamp or row['executed_at'],
           price_source=f"{row['source']} observed fill (rounded cents)",fill_id=fill_id,
           observation_id=row['observation_id'],knowledge_receipt=row['receipt_id'])


def completed_candles(db, account_id, *, as_of, receipt_cutoff, receipt_ids=None):
    """Called inside the paper transaction, at a live/replay knowledge boundary."""
    positions=db.execute('SELECT symbol,quantity FROM paper_positions WHERE account_id=? AND quantity>0',(account_id,)).fetchall()
    for position in positions:
        symbol=position['symbol']
        last_fill=db.execute('''SELECT f.executed_at FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id
          WHERE o.account_id=? AND o.symbol=? ORDER BY f.id DESC LIMIT 1''',(account_id,symbol)).fetchone()
        if last_fill is None: continue
        minutes=aggregate(db,symbol,as_of=as_of,receipt_cutoff=receipt_cutoff,replay_receipt_ids=receipt_ids)
        view=resample(minutes['candles'],symbol=symbol,timeframe='1m',as_of=as_of,minute_status=minutes['status'])
        last_mark=db.execute('SELECT candle_end FROM paper_pnl WHERE account_id=? AND symbol=? AND candle_end IS NOT NULL ORDER BY id DESC LIMIT 1',(account_id,symbol)).fetchone()
        for candle in view['candles']:
            stamp=candle['timestamp'];status=view['status'][stamp];end=status['interval_end']
            if not status['complete'] or utc(end)<=utc(last_fill['executed_at']): continue
            if last_mark and utc(end)<utc(last_mark['candle_end']): continue  # never move mark time backwards
            obs_id=minutes['status'][stamp]['observation_ids'][-1]
            obs=db.execute('SELECT source,source_time_ms FROM observations WHERE observation_id=?',(obs_id,)).fetchone()
            price_time=datetime.fromtimestamp(obs['source_time_ms']/1000,timezone.utc).isoformat().replace('+00:00','Z')
            # One row per candle close observation/version, independently of how often it is processed.
            append(db,account_id=account_id,symbol=symbol,key=f'candle:1m:{stamp}:close:{obs_id}',kind='completed candle',
                   event_time=as_of,price=Fraction(str(candle['close']))*100,price_time=price_time,
                   price_source=f"{obs['source']} completed 1m close",observation_id=obs_id,candle_timestamp=stamp,
                   candle_end=end,knowledge_receipt=receipt_cutoff)


def history(db, account_id):
    return [dict(row) for row in db.execute('SELECT * FROM paper_pnl WHERE account_id=? ORDER BY id',(account_id,))]


def current(db,account_id):
    rows=history(db,account_id)
    positions=db.execute('SELECT symbol,quantity FROM paper_positions WHERE account_id=? AND quantity>0',(account_id,)).fetchall()
    if rows: return rows[-1]
    return {'valuation_status':'unavailable' if positions else 'closed','price':None,'price_time':None,
            'price_source':None,'realized':0,'unrealized':None if positions else 0,'total':None if positions else 0}
