"""Disposable constructed-price tests, not actual trading or live evidence."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from backend.recorder import connect, record
from backend import paper


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'test.sqlite3'
        self.db=connect(self.path);paper.initialize(self.db);self.tick=0
    def tearDown(self): self.db.close();self.folder.cleanup()
    def send(self,action,quantity=None,request_id=None,account_id='live'):
        return paper.execute(self.db,request_id=request_id or f'req-{self.tick}-{action}-{self.db.total_changes}',action=action,quantity=quantity,account_id=account_id)
    def price(self,price,process=True):
        self.tick+=1
        result=record(self.db,{'id':'AAPL','price':price,'time':str(1794234600000+self.tick*1000),'test_data':True},f'2026-11-09T14:30:{self.tick:02d}Z')
        if process:paper.process_live(self.db)
        return result
    def test_reference_retry_empty_sale_restart(self):
        order=self.send('buy',4,'buy-4');self.assertEqual(order['status'],'pending')
        self.assertEqual(paper.snapshot(self.db)['fills'],[])
        self.price(100);self.assertEqual((paper.snapshot(self.db)['cash_cents'],paper.shares(self.db,'live','AAPL')),(60000,4))
        self.send('sell',1,'sell-1');self.price(110)
        self.assertEqual((paper.snapshot(self.db)['cash_cents'],paper.shares(self.db,'live','AAPL')),(71000,3))
        self.send('close',request_id='close');self.price(105)
        self.assertEqual(self.send('buy',4,'buy-4')['id'],order['id'])
        self.assertEqual(self.send('sell',1,'empty')['status'],'rejected')
        self.assertEqual(self.send('wait',request_id='wait')['status'],'no_order')
        env={**os.environ,'MARKET_DB_PATH':str(self.path)}
        out=subprocess.check_output([sys.executable,'-c','import json; from backend import paper; db=paper.open_account_db(); paper.process_live(db); print(json.dumps(paper.snapshot(db)))'],env=env,text=True)
        state=json.loads(out);self.assertEqual(state['cash_cents'],102500);self.assertEqual(len(state['fills']),3)
        self.assertEqual(len(state['orders']),4);self.assertEqual(state['positions'][0]['quantity'],0)
    def test_invalid_and_conflicting_retry(self):
        for i,qty in enumerate([0,-1,1.5,True,'4',None]):
            self.assertEqual(self.send('buy',qty,f'invalid-{i}')['status'],'rejected')
        self.send('buy',1,'stable')
        with self.assertRaises(ValueError):self.send('buy',2,'stable')
        self.assertEqual(len(paper.snapshot(self.db)['orders']),7)
    def test_fifo_cash_share_rechecks_and_noop(self):
        self.send('buy',8,'a');self.send('buy',8,'b');self.price(100)
        state=paper.snapshot(self.db);self.assertEqual([x['status'] for x in state['orders']],['filled','rejected'])
        self.assertEqual(self.send('hold',request_id='hold')['status'],'no_order')
        self.assertEqual(self.send('wait',request_id='wait')['status'],'rejected')
        self.send('sell',6,'c');self.send('sell',6,'d');self.price(100)
        self.assertEqual(paper.shares(self.db,'live','AAPL'),2)
        self.assertEqual(paper.snapshot(self.db)['orders'][-1]['rejection_reason'],'Insufficient shares at fill')
    def test_no_old_price_duplicate_or_invalid_fill(self):
        first=self.price(90);self.send('buy',1,'a')
        old=json.loads(self.db.execute('select payload_json from observations where observation_id=?',(first['observation_id'],)).fetchone()[0])
        record(self.db,old,'2026-11-09T14:30:20Z');paper.process_live(self.db)
        self.price(-1);self.assertEqual(paper.snapshot(self.db)['fills'],[])
        self.price(100.005);self.assertEqual(paper.snapshot(self.db)['fills'][0]['price_cents'],10001)
    def test_transaction_rollback_and_recovery(self):
        self.send('buy',4,'a');self.price(100,process=False)
        self.db.execute("CREATE TRIGGER fail_fill BEFORE INSERT ON paper_fills BEGIN SELECT RAISE(ABORT, 'constructed storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):paper.process_live(self.db)
        state=paper.snapshot(self.db);self.assertEqual(state['cash_cents'],100000);self.assertEqual(state['positions'],[]);self.assertEqual(state['orders'][0]['status'],'pending')
        self.db.execute('DROP TRIGGER fail_fill');paper.process_live(self.db)
        self.assertEqual(len(paper.snapshot(self.db)['fills']),1)
    def test_concurrent_retry_one_order(self):
        def submit(_):
            db=connect(self.path)
            try:return paper.execute(db,request_id='same',action='buy',quantity=1)['id']
            finally:db.close()
        with ThreadPoolExecutor(max_workers=4) as pool: ids=list(pool.map(submit,range(8)))
        self.assertEqual(len(set(ids)),1);self.price(100);self.assertEqual(len(paper.snapshot(self.db)['fills']),1)
    def test_replay_only_arrivals_and_no_rewind(self):
        for price in [100,110,105]:self.price(price)
        paper.start_replay(self.db,account_id='replay-test',symbol='AAPL',start='2026-11-09T14:30:00Z',end='2026-11-09T14:31:00Z',snapshot_cutoff=3)
        self.send('buy',4,'r1','replay-test');self.assertEqual(paper.snapshot(self.db,'replay-test')['fills'],[])
        first=paper.advance_replay(self.db,'replay-test',1);self.assertEqual(first['cash_cents'],60000)
        self.send('sell',1,'r2','replay-test');paper.advance_replay(self.db,'replay-test',2)
        self.send('close',request_id='r3',account_id='replay-test');last=paper.advance_replay(self.db,'replay-test',3)
        self.assertEqual(last['cash_cents'],102500);self.assertEqual(len(last['fills']),3)
        self.assertEqual(paper.advance_replay(self.db,'replay-test',3),last)
        with self.assertRaises(ValueError):paper.advance_replay(self.db,'replay-test',0)
        self.assertEqual(paper.snapshot(self.db)['fills'],[])

    def test_pending_order_recovers_after_process_restart(self):
        self.send('buy',4,'pending-restart');self.price(100,process=False)
        self.assertEqual(paper.snapshot(self.db)['fills'],[])
        env={**os.environ,'MARKET_DB_PATH':str(self.path)}
        command=[sys.executable,'-c','from backend import paper; db=paper.open_account_db(); paper.process_live(db); print(len(paper.snapshot(db)["fills"]))']
        self.assertEqual(subprocess.check_output(command,env=env,text=True).strip(),'1')
        self.assertEqual(subprocess.check_output(command,env=env,text=True).strip(),'1')
        self.assertEqual(paper.snapshot(self.db)['cash_cents'],60000)
