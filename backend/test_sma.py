"""Constructed reference data only; never modifies a captured session."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.sma import sma, with_sma
from backend.recorder import connect, record
from backend.replay import replay_view

CLOSES = [13, 10, 7, 13, 19, 7, 1]
EXPECTED = [(None,None,None),(11.5,None,None),(8.5,10,None),(10,10,None),(16,13,'up'),(13,13,None),(4,9,'down')]
START = datetime(2026,11,9,14,30,tzinfo=timezone.utc)
def stamp(i): return (START + timedelta(minutes=i)).isoformat().replace('+00:00','Z')
def seed(db):
    for i, price in enumerate(CLOSES):
        record(db, {'id':'AAPL','time':str(int((START+timedelta(minutes=i)).timestamp()*1000)),
                    'price':price, 'test_data':'SMA hand calculation'}, stamp(i+1))
def view(step):
    return with_sma(replay_view(symbol='AAPL',start=stamp(0),end=stamp(8),step=step),2,3)

class SmaTests(unittest.TestCase):
    def test_reference_batch_and_each_replay_prefix(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'MARKET_DB_PATH':str(Path(folder)/'test.sqlite3')}):
            db=connect(); seed(db)
            before=db.execute('select count(*) from deliveries').fetchone()[0]
            batch=view(7)['sma']['values']
            self.assertEqual([(r['short'],r['long'],r['signal']) for r in batch],EXPECTED)
            for step in range(8): self.assertEqual(view(step)['sma']['values'],batch[:step])
            self.assertEqual(db.execute('select count(*) from deliveries').fetchone()[0],before)
            # A correction first becomes knowable at receipt 8, never in earlier replay frames.
            record(db, {'id':'AAPL','time':str(int(START.timestamp()*1000)), 'price':20},stamp(7),
                   revision_of=1, revision_evidence='constructed correction')
            self.assertEqual(view(7)['sma']['values'],batch)
            self.assertNotEqual(view(8)['sma']['values'],batch)
            db.close()

    def test_unfinished_and_incomplete_do_not_signal(self):
        candles=[{'timestamp':stamp(i),'close':p} for i,p in enumerate(CLOSES)]
        status={r['timestamp']:{'complete':True} for r in candles}
        status[stamp(6)]={'complete':False,'ended':False}
        rows=sma(candles,status)['values']
        self.assertEqual(rows[-1],{'timestamp':stamp(6),'short':None,'long':None,'signal':None})
        status[stamp(6)]['ended']=True
        self.assertIsNone(sma(candles,status)['values'][-1]['signal'])

    def test_exact_comparison_and_initial_ties(self):
        prices=['1','1','1','1.00000000000000000001','0.99999999999999999999']
        candles=[{'timestamp':stamp(i),'close':p} for i,p in enumerate(prices)]
        rows=sma(candles,{r['timestamp']:{'complete':True} for r in candles},1,2)['values']
        self.assertIsNone(rows[3]['signal'])  # first non-equal pair establishes side
        self.assertEqual(rows[4]['signal'],'down')  # float display would round both to 1

    def test_invalid_windows(self):
        for a,b in [(0,3),(-1,3),(2,2),(3,2),(1.5,3),(True,3),('2',3)]:
            with self.assertRaises(ValueError): sma([],{},a,b)

    def test_long_independent_sql_reference_and_replay_prefixes(self):
        from backend.sma_reference import LONG_CLOSES, reference
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'MARKET_DB_PATH':str(Path(folder)/'test.sqlite3')}):
            db=connect()
            for i, price in enumerate(LONG_CLOSES):
                record(db, {'id':'AAPL','time':str(int((START+timedelta(minutes=i)).timestamp()*1000)),
                            'price':price},stamp(i+1))
            def selected(n):
                return replay_view(symbol='AAPL',start=stamp(0),end=stamp(40),step=n)
            batch=selected(30)
            expected=reference(batch['candles'],batch['status'],3,5)
            self.assertEqual(sma(batch['candles'],batch['status'],3,5)['values'],expected)
            for step in range(31):
                current=selected(step)
                self.assertEqual(sma(current['candles'],current['status'],3,5)['values'],expected[:step])
            self.assertEqual([(i,r['signal']) for i,r in enumerate(expected) if r['signal']],
                             [(10,'down'),(15,'up'),(21,'down'),(26,'up')])
            db.close()

    def test_duplicate_late_missing_revision_and_selection_isolation(self):
        from backend.sma_reference import reference
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'MARKET_DB_PATH':str(Path(folder)/'test.sqlite3')}):
            db=connect()
            def add(minute,price,receipt,symbol='AAPL',**kwargs):
                return record(db,{'id':symbol,'time':str(int((START+timedelta(minutes=minute)).timestamp()*1000)),
                                  'price':price},stamp(receipt),**kwargs)
            first=add(0,13,1);add(2,7,3);add(3,13,4);add(4,19,5)
            def selected(step,symbol='AAPL',timeframe='1m'):
                return replay_view(symbol=symbol,start=stamp(0),end=stamp(20),step=step,timeframe=timeframe)
            before=selected(4)
            self.assertEqual(len(before['candles']),4)  # minute 1 is absent, not zero-filled
            incomplete=selected(4,timeframe='5m')
            self.assertFalse(incomplete['status'][stamp(0)]['complete'])
            self.assertIsNone(sma(incomplete['candles'],incomplete['status'])['values'][0]['signal'])
            before_rows=sma(before['candles'],before['status'])['values']
            self.assertEqual(before_rows[-1]['short'],16)
            add(4,19,6)  # exact duplicate: no additional candle or SMA sample
            duplicate=selected(5)
            self.assertEqual(sma(duplicate['candles'],duplicate['status'])['values'],before_rows)
            add(1,10,7)  # late source minute fills the earlier gap only when received
            add(0,20,8,revision_of=first['observation_id'],revision_evidence='constructed correction')
            self.assertEqual(sma(selected(4)['candles'],selected(4)['status'])['values'],before_rows)
            for step in range(8):
                current=selected(step)
                self.assertEqual(sma(current['candles'],current['status'])['values'],
                                 reference(current['candles'],current['status']))
            self.assertEqual(selected(6)['candles'][0]['close'],13)
            self.assertEqual(selected(7)['candles'][0]['close'],20)
            # A separate supported symbol cannot borrow AAPL warm-up or crossover side.
            for i in range(5): add(i,100,i+1,symbol='SAMPLE')
            other=selected(5,'SAMPLE')
            self.assertTrue(all(r['signal'] is None for r in sma(other['candles'],other['status'])['values']))
            self.assertEqual(sma(other['candles'],other['status'])['values'][-1]['short'],100)
            higher=selected(7,timeframe='5m')
            self.assertEqual(len(higher['candles']),1)
            self.assertTrue(higher['status'][stamp(0)]['complete'])
            self.assertEqual(sma(higher['candles'],higher['status'])['values'][0]['short'],None)
            self.assertEqual(sma(selected(4)['candles'],selected(4)['status'])['values'],before_rows)
            db.close()
