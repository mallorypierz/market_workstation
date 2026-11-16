"""Constructed indicators and settings in isolated temporary databases."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from backend.indicators import calculate, catalog
from backend.indicator_store import add_instance, list_instances, with_indicators, settings_path
from backend.recorder import connect, record
from backend.replay import replay_view
from backend.test_sma import stamp, START
from datetime import timedelta


def fixture_candles():
    return [{'timestamp':stamp(i),'open':lo,'high':hi,'low':lo,'close':hi,'volume':1}
            for i,(hi,lo) in enumerate([(12,9),(15,10),(13,11)])]


def seed_range(db):
    for i,row in enumerate(fixture_candles()):
        for j,price in enumerate([row['low'],row['high']]):
            source=START+timedelta(minutes=i,seconds=j*20)
            receipt=START+timedelta(minutes=i+1,seconds=j)
            record(db,{'id':'AAPL','time':str(int(source.timestamp()*1000)), 'price':price,
                       'test_data':'CONSTRUCTED rolling range fixture'},receipt.isoformat())


class IndicatorTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MARKET_SETTINGS_DB_PATH':str(Path(self.folder.name)/'settings.sqlite3'),
                                      'MARKET_DB_PATH':str(Path(self.folder.name)/'market.sqlite3')})
        self.env.start()
    def tearDown(self):
        self.env.stop(); self.folder.cleanup()
    def add(self,name,kind='rolling_range',window=2):
        return add_instance('AAPL','yahoo','1m',name,kind,{'window':window})
    def test_range_and_shared_sma_warmup(self):
        candles=fixture_candles();status={c['timestamp']:{'complete':True} for c in candles}
        self.assertEqual([v['value'] for v in calculate('rolling_range',candles,status,{'window':2})],[None,6,5])
        self.assertEqual([v['value'] for v in calculate('rolling_range',candles,status,{'window':3})],[None,None,6])
        self.assertEqual([v['value'] for v in calculate('sma',candles,status,{'window':2})],[None,13.5,14])
        status[stamp(2)]['complete']=False
        self.assertIsNone(calculate('rolling_range',candles,status,{'window':2})[-1]['value'])
        self.assertEqual({c['type'] for c in catalog()},{'sma','rolling_range'})
    def test_settings_persist_isolate_and_reject_atomically(self):
        self.add('Range 2');self.add('Range 3',window=3); self.add('Average','sma',2)
        before=settings_path().read_bytes()
        for window in [0,-1,1.5,True,'2']:
            with self.assertRaises(ValueError): self.add('Bad',window=window)
        with self.assertRaises(ValueError): self.add('Range 2')
        with self.assertRaises(ValueError): self.add('Unknown','bad')
        self.assertEqual(settings_path().read_bytes(),before)
        output=subprocess.check_output([sys.executable,'-c',"import json; from backend.indicator_store import list_instances; print(json.dumps(list_instances('AAPL','yahoo','1m')))"],text=True)
        self.assertEqual([x['settings']['window'] for x in json.loads(output)],[2,3,2])
        self.assertEqual(list_instances('AAPL','yahoo','5m'),[])
        self.assertEqual(list_instances('SAMPLE','sample','1m'),[])
    def test_replay_uses_only_available_observations_and_revisions(self):
        self.add('Range 2');self.add('Range 3',window=3)
        db=connect();seed_range(db)
        def view(step): return with_indicators(replay_view(symbol='AAPL',start=stamp(0),end=stamp(5),step=step))
        earlier=view(4); final=view(6)
        self.assertEqual([i['values'][-1]['value'] for i in final['indicators']],[5,6])
        self.assertIsNone(earlier['indicators'][1]['values'][-1]['value'])
        record(db,{'id':'AAPL','time':str(int((START+timedelta(minutes=1,seconds=20)).timestamp()*1000)), 'price':20},stamp(4), revision_of=4,revision_evidence='constructed correction')
        self.assertEqual(view(6)['indicators'],final['indicators'])
        self.assertEqual([i['values'][-1]['value'] for i in view(7)['indicators']],[10,11])
        db.close()
    def test_edit_window_keeps_identity_and_other_settings(self):
        from backend.indicator_store import update_window
        first=self.add('Editable','sma',2);self.add('Other','sma',4)
        update_window(first['id'],{'window':3})
        values=list_instances('AAPL','yahoo','1m')
        self.assertEqual([v['settings']['window'] for v in values],[3,4])
        self.assertEqual(values[0]['id'],first['id'])
        with self.assertRaises(ValueError):update_window(first['id'],{'window':0})
        self.assertEqual(list_instances('AAPL','yahoo','1m'),values)
