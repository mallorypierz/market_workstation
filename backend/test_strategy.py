"""Deterministic strategy against isolated constructed receipts, no provider."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import timedelta
from backend import paper, strategy
from backend.recorder import connect, record
from backend.test_sma import START, stamp


def quote(db,minute,price,complete=True,**kwargs):
    source=START+timedelta(minutes=minute)
    receipt=source+timedelta(minutes=1) if complete else source+timedelta(seconds=10)
    result=record(db,{'id':'AAPL','price':price,'time':str(int(source.timestamp()*1000)),
                      'test_data':'CONSTRUCTED deterministic strategy'},receipt.isoformat(),**kwargs)
    return result


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'account.sqlite3'
        self.db=connect(self.path);paper.initialize(self.db);strategy.initialize(self.db)
        with patch('backend.paper.now',return_value=stamp(0)):
            strategy.start(self.db,{'run_id':'test','short':2,'long':3})
    def tearDown(self):self.db.close();self.folder.cleanup()
    def add(self,i,p,complete=True):
        result=quote(self.db,i,p,complete);paper.process_live(self.db);return result
    def state(self):return strategy.state(self.db,'test')
    def up(self,scale=1):
        for i,p in enumerate([13,10,7,13,19]):self.add(i,p*scale)
    def test_up_down_later_fill_and_account_trace(self):
        self.up();s=self.state()
        self.assertEqual([e['reason'] for e in s['events'][:2]],['SMA warm-up']*2)
        self.assertEqual(s['events'][2]['reason'],'No crossover')
        self.assertEqual(s['events'][-1]['order_status'],'pending');self.assertEqual(s['account']['fills'],[])
        self.add(5,100,False)
        self.assertEqual(self.state()['account']['cash_cents'],90000)
        self.add(5,7);self.add(6,1)
        self.assertEqual(self.state()['events'][-1]['action'],'close')
        self.assertEqual(self.state()['events'][-1]['order_status'],'pending')
        self.add(7,110,False);s=self.state()
        self.assertEqual((s['account']['cash_cents'],s['account']['pnl_current']['realized']),(101000,10))
        self.assertEqual(len(s['account']['fills']),2)
        for e in s['events']:
            if e['fill_id']:self.assertGreater(e['fill_receipt'],e['receipt_id'])
        self.assertEqual(paper.snapshot(self.db,'live')['orders'],[])
        with self.assertRaises(ValueError):paper.execute(self.db,request_id='manual',action='buy',quantity=1,account_id='strategy-test')
    def test_unfinished_duplicate_retry_restart_revision(self):
        for i,p in enumerate([13,10,7,13]):self.add(i,p)
        self.add(4,19,False)
        self.assertEqual(len(self.state()['events']),4);self.assertEqual(self.state()['account']['orders'],[])
        self.add(4,19)  # identical observation; later receipt establishes completion, but not a fill
        self.assertEqual(len(self.state()['account']['orders']),1)
        self.add(4,19);self.assertEqual(self.state()['account']['fills'],[])
        strategy.start(self.db,{'run_id':'test','short':2,'long':3})
        with self.assertRaises(ValueError):strategy.start(self.db,{'run_id':'test','short':1,'long':3})
        self.add(5,100,False);before=self.state()
        quote(self.db,0,20,revision_of=1,revision_evidence='explicit fixture correction')
        paper.process_live(self.db)
        self.assertEqual(self.state()['events'],before['events'])
        self.assertEqual(self.state()['account']['fills'],before['account']['fills'])
        env={**os.environ,'MARKET_DB_PATH':str(self.path)};env.pop('OPENAI_API_KEY',None)
        result=subprocess.check_output([sys.executable,'-c',"import json;from backend import paper,strategy;db=paper.open_account_db();strategy.initialize(db);paper.process_live(db);print(json.dumps(strategy.state(db,'test')))"],env=env,text=True)
        self.assertEqual(json.loads(result)['account']['fills'],before['account']['fills'])
        self.assertEqual(len(self.state()['account']['orders']),1)
    def test_insufficient_cash_and_fill_rejection(self):
        self.up(100);s=self.state()
        self.assertEqual(s['events'][-1]['reason'],'Insufficient cash at signal');self.assertEqual(s['account']['orders'],[])
        # Independent new run with low-price warm-up, later unaffordable execution quote.
        strategy.stop(self.db,'test')
        with patch('backend.paper.now',return_value=stamp(0)):
            strategy.start(self.db,{'run_id':'other','short':2,'long':3})
        for i,p in enumerate([13,10,7,13,19],start=5):self.add(i,p)
        self.add(10,2000,False)
        s=strategy.state(self.db,'other')
        self.assertEqual(s['account']['orders'][-1]['status'],'rejected')
        self.assertEqual(s['account']['orders'][-1]['rejection_reason'],'Insufficient cash at fill')
    def test_stop_cancels_pending_and_is_terminal(self):
        self.up();strategy.stop(self.db,'test');before=self.state()
        self.assertEqual(before['account']['orders'][0]['status'],'rejected')
        for i,p in enumerate([7,1,13,19,100],start=5):self.add(i,p)
        strategy.start(self.db,{'run_id':'test','short':2,'long':3})
        paper.process_live(self.db)
        self.assertFalse(self.state()['run']['enabled'])
        self.assertEqual(self.state()['events'],before['events']);self.assertEqual(self.state()['account']['fills'],[])
    def test_backlog_same_as_incremental_and_no_pyramiding(self):
        prices=[13,10,7,13,19,100,7,1,110,13,19]
        for i,p in enumerate(prices):self.add(i,p)
        expected=[(e['signal'],e['action'],e['receipt_id']) for e in self.state()['events']]
        with tempfile.TemporaryDirectory() as folder:
            db=connect(Path(folder)/'backlog.sqlite3');paper.initialize(db);strategy.initialize(db)
            with patch('backend.paper.now',return_value=stamp(0)):strategy.start(db,{'run_id':'test'})
            for i,p in enumerate(prices):quote(db,i,p)
            paper.process_live(db);actual=strategy.state(db,'test')
            self.assertEqual([(e['signal'],e['action'],e['receipt_id']) for e in actual['events']],expected)
            self.assertEqual([(f['receipt_id'],f['price_cents']) for f in actual['account']['fills']],[(f['receipt_id'],f['price_cents']) for f in self.state()['account']['fills']])
            self.assertTrue(all(o['quantity']==1 for o in actual['account']['orders']))
            db.close()
    def test_order_and_event_rollback_together(self):
        for i,p in enumerate([13,10,7,13]):self.add(i,p)
        self.db.execute("CREATE TRIGGER fail_strategy BEFORE INSERT ON sma_events BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        quote(self.db,4,19)
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):paper.process_live(self.db)
        self.assertEqual(self.state()['account']['orders'],[])
        self.db.execute('DROP TRIGGER fail_strategy');paper.process_live(self.db)
        self.assertEqual(len(self.state()['account']['orders']),1)

    def test_late_revision_cannot_pyramid_on_new_upward_signal(self):
        self.up();self.add(5,100,False)
        original=self.state()['account']['fills']
        # Revised history removes the old upward side; the next completed bar crosses up again.
        quote(self.db,4,1,revision_of=5,revision_evidence='constructed late correction')
        paper.process_live(self.db)
        self.add(5,100)
        s=self.state()
        self.assertEqual(s['events'][-1]['signal'],'up')
        self.assertEqual(s['events'][-1]['reason'],'Already holding; no pyramiding')
        self.assertEqual(s['account']['fills'],original)
        self.assertEqual(len(s['account']['orders']),1)
