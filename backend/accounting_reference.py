"""Constructed accounting audit fixtures and independent hand-calculated expectations."""
import hashlib
import json
from backend import paper
from backend.pnl_fixture import build, quote, submit, process_at, at
from backend.recorder import record
from datetime import datetime

FIELDS=['cash_cents','quantity','average_cost_exact','realized_exact','unrealized_exact','total_exact']
EXPECTED={
 'standard':[(60000,4,'10000','0','0','0'),(60000,4,'10000','0','4000','4000'),
             (71000,3,'10000','1000','3000','4000'),(71000,3,'10000','1000','-1500','-500'),
             (102500,0,None,'2500','0','2500')],
 'multiple':[(79998,2,'10001','0','0','0'),(69897,3,'30103/3','0','200','200'),
             (80098,2,'30103/3','500/3','1000/3','500'),
             (80098,2,'30103/3','500/3','1669/3','723')],
 'unavailable':[(60000,4,'10000','0','0','0'),(60000,4,'10000','0','4000','4000'),
                (60000,4,'10000','0',None,None)]}
# Expected equity in cents, derived from starting cash plus exact total P&L.
EQUITY={'standard':['100000','104000','104000','99500','102500'],
        'multiple':['100000','100200','100500','100723'],
        'unavailable':['100000','104000',None]}


def source_digest(db):
    # Hash every stored field, including raw payloads, identity, receipts and revisions.
    data={table:[tuple(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
          for table in ['observations','deliveries','revisions']}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def build_case(db,case):
    if case=='standard':return build(db)
    paper.initialize(db)
    if case=='multiple':
        submit(db,'buy',2,'14:30:00','round-buy1');quote(db,100.005,'14:30:05')
        submit(db,'buy',1,'14:30:06','round-buy2');quote(db,101.014,'14:30:10')
        submit(db,'sell',1,'14:30:11','round-sell');quote(db,102.005,'14:30:15')
        quote(db,103.125,'14:30:50');process_at(db,'14:31:00')
    elif case=='unavailable':
        submit(db,'buy',4,'14:30:00','unknown-buy');quote(db,100,'14:30:05')
        last=quote(db,110,'14:30:50');process_at(db,'14:31:00')
        record(db,{'id':'AAPL','price':-1,'time':str(int(datetime.fromisoformat(at('14:30:50').replace('Z','+00:00')).timestamp()*1000)),
                   'test_data':'CONSTRUCTED invalid valuation'},at('14:31:05'),
               revision_of=last['observation_id'],revision_evidence='constructed invalid correction')
        process_at(db,'14:31:05')
    else:raise ValueError('Unknown accounting fixture')
    return paper.snapshot(db)
