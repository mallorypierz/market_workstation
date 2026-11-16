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
