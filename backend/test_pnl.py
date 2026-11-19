"""Weighted-average accounting, valuation causality and durable event deduplication."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from backend import paper,pnl
from backend.recorder import connect,record
from backend.pnl_fixture import build,quote,submit,process_at,at
from unittest.mock import patch

class PnlTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'test.sqlite3'
        self.db=connect(self.path);paper.initialize(self.db)
    def tearDown(self):self.db.close();self.folder.cleanup()
    def test_reference_dedup_and_process_restart(self):
        rows=build(self.db)['pnl_history']
        expected=[(60000,4,0,0,0),(60000,4,0,40,40),(71000,3,10,30,40),(71000,3,10,-15,-5),(102500,0,25,0,25)]
        self.assertEqual([tuple(r[k] for k in ['cash_cents','quantity','realized','unrealized','total']) for r in rows],expected)
        process_at(self.db,'14:33:00');paper.initialize(self.db)
        self.assertEqual(pnl.history(self.db,'live'),rows)
        env={**os.environ,'MARKET_DB_PATH':str(self.path)}
        output=subprocess.check_output([sys.executable,'-c',"import json;from backend import paper; db=paper.open_account_db();paper.process_live(db);print(json.dumps(paper.snapshot(db)['pnl_history']))"],env=env,text=True)
        self.assertEqual(json.loads(output),rows)
    def test_weighted_buys_partial_sale_exact_fraction(self):
        submit(self.db,'buy',2,'14:30:00','b1');quote(self.db,100,'14:30:05')
        submit(self.db,'buy',1,'14:30:06','b2');quote(self.db,101,'14:30:10')
        submit(self.db,'sell',1,'14:30:11','s1');quote(self.db,102,'14:30:15')
        rows=pnl.history(self.db,'live')
        self.assertEqual(rows[-1]['average_cost_exact'],'30100/3')
        self.assertEqual(rows[-1]['realized_exact'],'500/3')
        self.assertEqual(rows[-1]['quantity'],2)
        self.assertEqual(rows[-2]['average_cost_exact'],rows[-1]['average_cost_exact'])
        self.assertEqual(rows[-1]['total'],5)
    def test_unfinished_unusable_and_candle_revision(self):
        submit(self.db,'buy',4,'14:30:00','b1');quote(self.db,100,'14:30:05')
        last=quote(self.db,110,'14:30:50')
        self.assertEqual(len(pnl.history(self.db,'live')),1)
        process_at(self.db,'14:31:00');process_at(self.db,'14:31:00')
        self.assertEqual(len(pnl.history(self.db,'live')),2)
        payload={'id':'AAPL','price':-1,'time':str(int(__import__('datetime').datetime.fromisoformat(at('14:30:50').replace('Z','+00:00')).timestamp()*1000))}
        record(self.db,payload,at('14:31:05'),revision_of=last['observation_id'],revision_evidence='constructed invalid correction')
        process_at(self.db,'14:31:05')
        rows=pnl.history(self.db,'live');self.assertEqual(len(rows),3)
        self.assertEqual(rows[-1]['valuation_status'],'unavailable');self.assertIsNone(rows[-1]['unrealized']);self.assertIsNone(rows[-1]['total'])
        self.assertEqual(rows[1]['unrealized'],40)
    def test_fill_and_pnl_rollback_together(self):
        submit(self.db,'buy',4,'14:30:00','b1')
        self.db.execute("CREATE TRIGGER fail_pnl BEFORE INSERT ON paper_pnl BEGIN SELECT RAISE(ABORT,'constructed PNL failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):quote(self.db,100,'14:30:05')
        state=paper.snapshot(self.db);self.assertEqual(state['cash_cents'],100000);self.assertEqual(state['fills'],[]);self.assertEqual(state['pnl_history'],[])
        self.assertEqual(state['orders'][0]['status'],'pending')
        self.assertEqual(state['positions'],[])
        self.assertEqual(state['cursor'],0)
        self.db.execute('DROP TRIGGER fail_pnl');process_at(self.db,'14:30:05')
        self.assertEqual(len(pnl.history(self.db,'live')),1)
    def test_upgrade_backfills_only_fills(self):
        build(self.db);self.db.execute('DROP TABLE paper_pnl');paper.initialize(self.db)
        rows=pnl.history(self.db,'live');self.assertEqual(len(rows),3);self.assertEqual(rows[-1]['realized'],25)
        self.assertTrue(all(r['fill_id'] for r in rows))
    def test_replay_does_not_use_future_completed_close(self):
        for p,t in [(100,'14:30:05'),(110,'14:30:50'),(95,'14:31:05')]:quote(self.db,p,t)
        paper.start_replay(self.db,account_id='replay-pnl',symbol='AAPL',start=at('14:30:00'),end=at('14:32:00'),snapshot_cutoff=3)
        paper.execute(self.db,request_id='rb',action='buy',quantity=4,account_id='replay-pnl')
        one=paper.advance_replay(self.db,'replay-pnl',1);self.assertEqual(len(one['pnl_history']),1)
        two=paper.advance_replay(self.db,'replay-pnl',2);self.assertEqual(len(two['pnl_history']),1)
        three=paper.advance_replay(self.db,'replay-pnl',3);self.assertEqual(three['pnl_history'][-1]['price'],110)
        self.assertEqual(three['pnl_history'][-1]['unrealized'],40)
        self.assertEqual(paper.advance_replay(self.db,'replay-pnl',3)['pnl_history'],three['pnl_history'])

    def test_independent_rounding_equity_and_source_immutability(self):
        from fractions import Fraction
        from backend.accounting_reference import build_case,EXPECTED,EQUITY,FIELDS,source_digest
        state=build_case(self.db,'multiple');rows=state['pnl_history']
        self.assertEqual([tuple(r[k] for k in FIELDS) for r in rows],EXPECTED['multiple'])
        self.assertEqual([f['price_cents'] for f in state['fills']],[10001,10101,10201])
        for row,expected in zip(rows,EQUITY['multiple']):
            equity=Fraction(row['cash_cents'])+row['quantity']*Fraction(row['price_exact'])
            self.assertEqual(equity,Fraction(expected))
            self.assertEqual(Fraction(row['total_exact']),Fraction(row['realized_exact'])+Fraction(row['unrealized_exact']))
            self.assertEqual(equity-100000,Fraction(row['total_exact']))
        digest=source_digest(self.db)
        # Retry is idempotent; rejection and polling must not rewrite source records or P&L.
        retry=submit(self.db,'sell',1,'14:31:01','round-sell')
        self.assertEqual(retry['id'],state['orders'][-1]['id'])
        rejected=submit(self.db,'sell',3,'14:31:02','oversell')
        self.assertEqual(rejected['status'],'rejected')
        process_at(self.db,'14:32:00');paper.initialize(self.db)
        self.assertEqual(pnl.history(self.db,'live'),rows)
        self.assertEqual(source_digest(self.db),digest)
        self.assertTrue(all(r[0]>=0 for r in self.db.execute('SELECT cash_cents FROM paper_accounts')))
        self.assertTrue(all(r[0]>=0 for r in self.db.execute('SELECT quantity FROM paper_positions')))

    def test_reference_equity_and_unavailable_totals(self):
        from fractions import Fraction
        from backend.accounting_reference import build_case,EXPECTED,EQUITY,FIELDS
        for case in ['standard','unavailable']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                db=connect(Path(folder)/'audit.sqlite3')
                rows=build_case(db,case)['pnl_history']
                self.assertEqual([tuple(r[k] for k in FIELDS) for r in rows],EXPECTED[case])
                for row,expected in zip(rows,EQUITY[case]):
                    if expected is None:
                        self.assertEqual(row['valuation_status'],'unavailable')
                        self.assertIsNone(row['unrealized']);self.assertIsNone(row['total'])
                    else:
                        equity=Fraction(row['cash_cents'])+row['quantity']*Fraction(row['price_exact'])
                        self.assertEqual(equity,Fraction(expected))
                        self.assertEqual(equity-100000,Fraction(row['total_exact']))
                        self.assertEqual(Fraction(row['total_exact']),Fraction(row['realized_exact'])+Fraction(row['unrealized_exact']))
                db.close()
