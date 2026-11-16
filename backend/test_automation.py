import copy
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from backend import automation,paper,decisions
from backend.recorder import connect,record
from backend.test_chart_analysis import png


def at(t):return '2026-11-09T'+t+'Z'
def provider(payload):
    q=payload['questions'][0]['name']
    return {'answers':[{'name':'review_verdict','type':'choice','choice':'accept'}]} if q=='review_verdict' else {'answers':[{'name':n,'type':'choice','choice':v} for n,v in [('action','buy'),('crossover','up'),('evidence','sufficient')]]}

class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'auto.sqlite3'
        self.env=patch.dict(os.environ,{'MARKET_DB_PATH':str(self.path),'MARKET_AUTOMATION_TEST':'1','MARKET_SETTINGS_DB_PATH':str(Path(self.folder.name)/'settings.sqlite3')});self.env.start()
        self.clock=patch('backend.paper.now',return_value=at('14:34:55'));self.now=self.clock.start()
        self.db=connect(self.path);paper.initialize(self.db);automation.initialize(self.db)
        for i,p in enumerate([13,10,7,13,19]):self.quote(p,f'14:{30+i:02}:50')
        self.state=automation.start(self.db,{'short':2,'long':3});self.c=self.state['control']
        self.now.return_value=at('14:35:01')
    def tearDown(self):self.db.close();self.clock.stop();self.env.stop();self.folder.cleanup()
    def quote(self,price,time):
        stamp=at(time);record(self.db,{'id':'AAPL','price':price,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)),'test_data':'CONSTRUCTED AUTOMATION'},stamp)
    def reserve(self):return automation.reserve(self.db,self.c['id'],{'generation':self.c['generation'],'candle_timestamp':at('14:34:00')})
    def approved(self):
        j=self.reserve();r=automation.submit(self.db,j['id'],{'image':png(j['snapshot'])},provider);self.assertEqual(r['status'],'pending');return r
    def test_once_fill_links_balance_pnl_and_restart(self):
        j=self.approved();self.assertEqual(automation.apply(self.db,j['id'])['order_id'],j['order_id'])
        self.now.return_value=at('14:35:10');self.quote(20,'14:35:10');paper.process_live(self.db)
        filled=automation.job(self.db,j['id']);self.assertEqual(filled['status'],'filled')
        state=paper.snapshot(self.db,'automation-test');self.assertEqual((state['cash_cents'],state['positions'][0]['quantity'],len(state['fills'])),(98000,1,1))
        self.assertEqual(state['fills'][0]['decision_id'],j['decision_id']);self.assertEqual(state['pnl_history'][0]['decision_id'],j['decision_id'])
        self.assertEqual(paper.snapshot(self.db,'live')['cash_cents'],100000)
        self.db.close();self.db=connect(self.path);paper.initialize(self.db);automation.startup(self.db)
        self.assertEqual(automation.apply(self.db,j['id'])['status'],'filled');paper.process_live(self.db)
        self.assertEqual(len(paper.snapshot(self.db,'automation-test')['fills']),1)
    def test_veto_missing_image_and_duplicate_claim(self):
        j=self.reserve();duplicate=self.reserve();self.assertEqual(j['id'],duplicate['id'])
        def veto(p):return {'answers':[{'name':'review_verdict','type':'choice','choice':'reject_unsupported_signal'}]} if p['questions'][0]['name']=='review_verdict' else provider(p)
        r=automation.submit(self.db,j['id'],{'image':png(j['snapshot'])},veto)
        self.assertEqual(r['status'],'skipped');self.assertEqual(self.db.execute('select count(*) from paper_orders').fetchone()[0],0)
        self.assertEqual(automation.submit(self.db,j['id'],{'image':None},provider)['decision_id'],r['decision_id'])
    def test_stop_during_provider_and_pending_order(self):
        j=self.reserve()
        def stopped(p):
            db=connect(self.path)
            try:automation.stop(db,self.c['id'])
            finally:db.close()
            return provider(p)
        r=automation.submit(self.db,j['id'],{'image':png(j['snapshot'])},stopped)
        self.assertEqual(r['status'],'skipped');self.assertEqual(self.db.execute('select count(*) from paper_orders').fetchone()[0],0)
    def test_expiry_and_cash_recheck(self):
        j=self.approved();self.now.return_value=at('14:37:01');self.quote(20,'14:37:01');paper.process_live(self.db)
        self.assertIn('expired',automation.job(self.db,j['id'])['reason']);self.assertEqual(self.db.execute('select count(*) from paper_fills').fetchone()[0],0)
    def test_fill_failure_rolls_back_all_linked_writes(self):
        j=self.approved();self.db.execute("CREATE TRIGGER fail_auto BEFORE UPDATE OF fill_id ON automation_jobs BEGIN SELECT RAISE(ABORT,'constructed failure'); END")
        self.now.return_value=at('14:35:10');self.quote(20,'14:35:10')
        with self.assertRaises(sqlite3.IntegrityError):paper.process_live(self.db)
        self.assertEqual(paper.account(self.db,'automation-test')['cash_cents'],100000)
        self.assertEqual(self.db.execute('select count(*) from paper_fills').fetchone()[0],0)
        self.assertEqual(self.db.execute('select count(*) from paper_pnl').fetchone()[0],0)

    def test_stop_cancels_pending(self):
        j=self.approved();automation.stop(self.db,self.c['id'])
        self.now.return_value=at('14:35:10');self.quote(20,'14:35:10');paper.process_live(self.db)
        self.assertEqual(automation.job(self.db,j['id'])['status'],'skipped')
        self.assertEqual(paper.account(self.db,'automation-test')['cash_cents'],100000)
        self.assertEqual(self.db.execute('select count(*) from paper_fills').fetchone()[0],0)
    def test_price_jump_rechecks_cash(self):
        j=self.approved();self.now.return_value=at('14:35:10');self.quote(2000,'14:35:10');paper.process_live(self.db)
        self.assertEqual(automation.job(self.db,j['id'])['status'],'skipped')
        self.assertEqual(paper.account(self.db,'automation-test')['cash_cents'],100000)
        self.assertEqual(self.db.execute('select count(*) from paper_fills').fetchone()[0],0)
    def test_missing_capture_records_failure(self):
        j=self.reserve();r=automation.submit(self.db,j['id'],{'image':None},provider)
        self.assertEqual(r['status'],'skipped');self.assertIsNotNone(r['decision_id'])
        self.assertEqual(self.db.execute('select count(*) from paper_orders').fetchone()[0],0)
    def test_equivalent_timestamp_deduplicates(self):
        j=self.reserve();r=automation.reserve(self.db,self.c['id'],{'generation':self.c['generation'],'candle_timestamp':'2026-11-09T14:34:00+00:00'})
        self.assertEqual(j['id'],r['id'])
