"""Build the labeled five-event P&L example in a new disposable database."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from backend.recorder import connect, record
from backend import paper


def at(time): return f'2026-11-09T{time}Z'

def process_at(db,time):
    with patch('backend.paper.now',return_value=at(time)): paper.process_live(db)


def quote(db,price,time):
    stamp=at(time)
    stored=record(db,{'id':'AAPL','price':price,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)),
                      'test_data':'CONSTRUCTED PNL FIXTURE'},stamp,source='yahoo')
    process_at(db,time);return stored


def submit(db,action,quantity,time,request_id):
    with patch('backend.paper.now',return_value=at(time)):
        return paper.execute(db,request_id=request_id,action=action,quantity=quantity)


def build(db):
    paper.initialize(db)
    submit(db,'buy',4,'14:30:00','pnl-buy');quote(db,100,'14:30:05')
    quote(db,110,'14:30:50');process_at(db,'14:31:00')
    submit(db,'sell',1,'14:31:01','pnl-sell');quote(db,110,'14:31:05')
    quote(db,95,'14:31:50');process_at(db,'14:32:00')
    submit(db,'close',None,'14:32:01','pnl-close');quote(db,105,'14:32:05')
    return paper.snapshot(db)


def main():
    folder=Path(tempfile.mkdtemp(prefix='pnl-fixture-'));path=folder/'account.sqlite3'
    db=connect(path)
    try:
        state=build(db)
        print(json.dumps({'database':str(path),'label':'CONSTRUCTED ZERO-FEE PNL EXAMPLE',
              'rows':[{k:r[k] for k in ['event_type','cash_cents','quantity','realized','unrealized','total']} for r in state['pnl_history']]},indent=2))
    finally: db.close()

if __name__=='__main__': main()
