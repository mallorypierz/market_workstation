"""Hand-verifiable causal backtests with isolated source and account databases."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import backtest
from backend.recorder import connect,record
from backend.test_strategy import quote
from backend.test_sma import stamp
from backend.accounting_reference import source_digest


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'MARKET_BACKTEST_DIR':str(self.base/'runs')});self.env.start()
        self.source=self.base/'source.sqlite3';self.db=connect(self.source)
        self.config={'warmup_start':stamp(0),'start':stamp(0),'end':stamp(10),'short':2,'long':3}
    def tearDown(self):self.db.close();self.env.stop();self.temp.cleanup()
    def run_bt(self,name='one',**kwargs):return backtest.run(name,{**self.config,**kwargs},source=self.source)['result']
    def seed(self):
        for i,p in enumerate([13,10,7,13,19]):quote(self.db,i,p)
        quote(self.db,5,100,False);quote(self.db,5,7);quote(self.db,6,1);quote(self.db,7,110,False)
    def test_known_account_performance_and_isolation(self):
        self.seed();before=source_digest(self.db);r=self.run_bt()
        self.assertEqual(r['account']['cash_cents'],101000)
        self.assertEqual(r['account']['pnl_current']['realized'],10)
        self.assertEqual(r['ending_equity'],1010);self.assertAlmostEqual(r['total_return'],.01)
        self.assertAlmostEqual(r['max_drawdown'],.099)
        self.assertEqual(r['equity_curve'][0]['equity'],1000)
        self.assertEqual([(f['price_cents'],f['quantity']) for f in r['account']['fills']],[(10000,1),(11000,1)])
        for e in r['decisions']:
            if e['fill']:self.assertGreater(e['fill']['receipt_id'],e['receipt_id'])
        self.assertEqual(before,source_digest(self.db))
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_accounts'").fetchone())
        self.assertEqual(backtest.read('one')['status'],'completed')
    def test_no_trades_and_inadequate_warmup(self):
        for i in range(6):quote(self.db,i,10)
        r=self.run_bt();self.assertEqual(r['account']['fills'],[]);self.assertEqual(r['total_return'],0);self.assertEqual(r['max_drawdown'],0)
        small=self.run_bt('small',start=stamp(4),warmup_start=stamp(4),end=stamp(6))
        self.assertTrue(all(e['reason']=='SMA warm-up' for e in small['decisions']))
    def test_warmup_has_no_trades_and_snapshot_freezes(self):
        self.seed();r=self.run_bt(start=stamp(5))
        self.assertFalse(any(e['timestamp']<stamp(5) for e in r['decisions']))
        self.assertEqual(r['account']['fills'],[])  # warm-up up-cross does not buy retroactively
        saved=backtest.read('one');quote(self.db,8,999)
        self.assertEqual(self.run_bt(start=stamp(5)),r)
        self.assertEqual(backtest.read('one')['metadata']['dataset_sha256'],saved['metadata']['dataset_sha256'])
        with self.assertRaises(ValueError):self.run_bt(start=stamp(4))
    def test_no_next_price_remains_pending_and_end_mark(self):
        for i,p in enumerate([13,10,7,13,19]):quote(self.db,i,p)
        r=self.run_bt();self.assertEqual(len(r['pending_orders']),1);self.assertEqual(r['account']['fills'],[])
        quote(self.db,5,100,False)
        r=self.run_bt('open');self.assertEqual(r['open_positions'][0]['quantity'],1)
        self.assertEqual(r['ending_equity'],919);self.assertEqual(r['account']['pnl_current']['unrealized'],-81)
        self.assertEqual(r['equity_curve'][-1]['mark']['close'],19) # latest known completed, not unfinished100
    def test_future_changes_preserve_earlier_decisions_and_fills(self):
        self.seed();r=self.run_bt()
        quote(self.db,4,1,revision_of=5,revision_evidence='late correction')
        quote(self.db,8,999)
        changed=self.run_bt('changed')
        cutoff=9
        # Compare the evidence frozen at decision time, not the later joined order/fill outcome.
        def past(result):return [{k:v for k,v in e.items() if k not in ('order','fill')} for e in result['decisions'] if e['receipt_id']<=cutoff]
        self.assertEqual(past(r),past(changed))
        def fills(result):return [{k:v for k,v in f.items() if k!='processed_at'} for f in result['account']['fills'] if f['receipt_id']<=cutoff]
        self.assertEqual(fills(r),fills(changed))
    def test_duplicate_out_of_order_and_repeatability(self):
        self.seed();quote(self.db,7,110,False) # duplicate cannot execute twice
        quote(self.db,1,20) # late source/receipt-time regression must not move clock back
        one=self.run_bt();two=self.run_bt('two')
        self.assertEqual(one['equity_curve'],two['equity_curve'])
        self.assertEqual(one['total_return'],two['total_return'])
        self.assertEqual(len(one['account']['fills']),2)
        self.assertEqual([e['timestamp'] for e in one['decisions']],[e['timestamp'] for e in two['decisions']])
    def bars(self):
        dates=['2026-11-02','2026-11-03','2026-11-04','2026-11-05','2026-11-06','2026-11-09','2026-11-10','2026-11-11']
        closes=[13,10,7,13,19,7,1,13];opens=[13,10,7,13,19,100,7,110]
        return {'kind':'synthetic_daily_bars','symbol':'AAPL','source':'hand-worked fixture','bars':[
            {'date':d,'open':o,'high':max(o,c),'low':min(o,c),'close':c,'volume':100,'dividends':0,'splits':0} for d,o,c in zip(dates,opens,closes)]}
    def test_daily_open_execution_and_causality(self):
        request={'start':'2026-11-05T14:30:00Z','warmup_start':'2026-11-02T14:30:00Z','end':'2026-11-12T00:00:00Z','timeframe':'1d'}
        bars=self.bars();one=backtest.run('bars',request,bars=bars)['result']
        self.assertEqual(one['account']['cash_cents'],101000);self.assertEqual(one['ending_equity'],1010)
        self.assertEqual([f['price_cents'] for f in one['account']['fills']],[10000,11000])
        self.assertEqual(one['sample']['warmup_completed_candles'],3)
        self.assertTrue(all(e['timestamp']>=request['start'] for e in one['decisions']))
        changed=copy.deepcopy(bars);changed['bars'][-1].update(close=999,high=999)
        two=backtest.run('bars2',request,bars=changed)['result']
        self.assertEqual([{k:v for k,v in f.items() if k!='processed_at'} for f in one['account']['fills']],
                         [{k:v for k,v in f.items() if k!='processed_at'} for f in two['account']['fills']])
        self.assertEqual(one['equity_curve'][:-1],two['equity_curve'][:-1])
    def test_input_validation_and_empty_selection(self):
        empty=self.run_bt();self.assertEqual(empty['ending_equity'],1000);self.assertIn('No evaluated candles',empty['warnings'])
        with self.assertRaises(ValueError):self.run_bt('../bad')
        with self.assertRaises(ValueError):self.run_bt('bad',short=0)
        with self.assertRaises(ValueError):self.run_bt('bad',initial_cash_cents=-1)
        bars=self.bars();bars['bars'][0]['splits']=2
        with self.assertRaises(ValueError):backtest.run('split',{'start':'2026-11-02T00:00:00Z','end':'2026-11-12T00:00:00Z','timeframe':'1d'},bars=bars)

    def test_daily_last_signal_has_no_invented_fill(self):
        bars=self.bars();bars['bars']=bars['bars'][:5]
        request={'start':'2026-11-05T14:30:00Z','warmup_start':'2026-11-02T14:30:00Z','end':'2026-11-12T00:00:00Z','timeframe':'1d'}
        r=backtest.run('bar-pending',request,bars=bars)['result']
        self.assertEqual(len(r['pending_orders']),1)
        self.assertEqual(r['account']['fills'],[])
        self.assertEqual(r['ending_equity'],1000)
