"""Causal snapshots, action validation, persisted failures, and no account mutations."""
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend import decisions, paper
from backend.decision_fixture import build
from backend.recorder import connect, record


def answer(action='wait'):
    return {'answers':[{'name':'paper_action','type':'choice','choice':action}]}


def ledger(db):
    return {table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in
            ['paper_accounts','paper_positions','paper_orders','paper_fills','paper_requests','paper_pnl']}


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'fixture.sqlite3'
        self.db=connect(self.path);self.snapshot=build(self.db)
    def tearDown(self): self.db.close();self.folder.cleanup()
    def decide(self,action):
        return decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']},lambda payload:answer(action))
    def test_fixed_snapshot_and_no_mutation(self):
        before=ledger(self.db);s=self.snapshot
        self.assertTrue(s['complete']);self.assertFalse(s['order_eligible']);self.assertEqual(s['kind'],'test')
        self.assertEqual(s['candle']['close'],19)
        self.assertEqual(s['indicators']['at_candle'],{'timestamp':'2026-11-09T14:34:00Z','short':16,'long':13,'signal':'up'})
        self.assertEqual(len(s['chart']['candles']),5)
        self.assertEqual(s['knowledge']['receipt_cutoff'],5)
        result=self.decide('buy');self.assertEqual(result['status'],'valid');self.assertEqual(result['proposal']['quantity'],1)
        self.assertFalse(result['order_eligible']);self.assertEqual(ledger(self.db),before)
        self.db.close();self.db=connect(self.path)
        self.assertEqual(decisions.get_decision(self.db,result['decision_id']),result)
        self.assertEqual(decisions.get_snapshot(self.db,s['snapshot_id']),s)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE decision_snapshots SET digest='changed'")
        self.db.rollback()
    def test_action_rules_and_valid_hold(self):
        self.assertEqual(self.decide('wait')['status'],'valid')
        for action in ['hold','close','sell']:self.assertEqual(self.decide(action)['status'],'invalid_proposal')
        s={**self.snapshot,'account':{**self.snapshot['account'],'shares':4,'cash':10,'cash_cents':1000},'order_size':2}
        self.snapshot=decisions.save_snapshot(self.db,s)
        self.assertEqual(self.decide('hold')['status'],'valid')
        self.assertEqual(self.decide('wait')['status'],'invalid_proposal')
        self.assertEqual(self.decide('buy')['status'],'invalid_proposal')
        self.assertEqual(self.decide('sell')['proposal']['quantity'],2)
        self.assertEqual(self.decide('close')['proposal']['quantity'],4)
    def test_failures_persist_without_keys(self):
        before=ledger(self.db)
        def timeout(_):raise TimeoutError('SECRET MUST NOT BE LOGGED')
        result=decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']},timeout)
        self.assertEqual(result['status'],'timeout');self.assertNotIn('SECRET',json.dumps(result))
        for response in [{},answer(True),answer('short'),{'answers':[{'name':'wrong','type':'choice','choice':'buy'}]}]:
            r=decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']},lambda _:response)
            self.assertEqual(r['status'],'malformed_answer')
        r=decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']},lambda _:{'answers':[{'name':'paper_action','type':'refusal'}]})
        self.assertEqual(r['status'],'refused')
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            r=decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']})
        self.assertEqual(r['status'],'configuration_error');self.assertEqual(r['model_call'],'not_called')
        self.assertEqual(ledger(self.db),before)
    def test_missing_and_warmup_input_no_provider(self):
        with patch('backend.decisions.openai_request') as provider:
            self.assertEqual(decisions.decide(self.db,{})['status'],'missing_input')
            s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:30:00Z'})
            self.assertFalse(s['complete'])
            self.assertEqual(decisions.decide(self.db,{'snapshot_id':s['snapshot_id']})['status'],'missing_input')
            provider.assert_not_called()
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:30:00Z','interval':'5m'})
        self.assertFalse(s['complete'])  # SMA warmup, despite full five-minute coverage
    def test_late_revision_and_future_fill_cannot_change_frozen_close(self):
        original=self.snapshot
        payload={'id':'AAPL','price':999,'time':str(int(datetime(2026,11,9,14,34,50,tzinfo=timezone.utc).timestamp()*1000))}
        record(self.db,payload,'2026-11-09T14:35:00.000001Z',revision_of=5,revision_evidence='constructed late correction')
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertEqual(s['candle'],original['candle']);self.assertEqual(s['indicators'],original['indicators'])
        self.assertEqual(s['revisions'],[])
        # Actual future fills affect today's balances, never the historical close snapshot.
        with patch('backend.paper.now',return_value='2026-11-09T14:38:00Z'):
            paper.execute(self.db,request_id='future-buy',action='buy',quantity=2)
        record(self.db,{'id':'AAPL','price':100,'time':'1794235140000'},'2026-11-09T14:39:00Z')
        with patch('backend.paper.now',return_value='2026-11-09T14:39:00Z'):paper.process_live(self.db)
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertEqual(s['account']['cash_cents'],100000);self.assertEqual(s['account']['shares'],0)
        self.assertEqual(decisions.get_snapshot(self.db,original['snapshot_id']),original)
    def test_replay_revealed_boundary(self):
        paper.start_replay(self.db,account_id='replay-decision',symbol='AAPL',start='2026-11-09T14:30:00Z',end='2026-11-09T14:40:00Z',snapshot_cutoff=7)
        paper.advance_replay(self.db,'replay-decision',5)
        s=decisions.create_snapshot(self.db,{'account_id':'replay-decision','candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertFalse(s['complete'])  # replay clock14:34:50 has not reached close
        paper.advance_replay(self.db,'replay-decision',6)
        s=decisions.create_snapshot(self.db,{'account_id':'replay-decision','candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertTrue(s['complete']);self.assertEqual(s['knowledge']['receipt_ids'],[1,2,3,4,5])
        self.assertEqual(s['candle']['close'],19)
    def test_microsecond_late_correction_and_replay_account_origin(self):
        payload={'id':'AAPL','price':999,'time':str(int(datetime(2026,11,9,14,36,50,tzinfo=timezone.utc).timestamp()*1000))}
        record(self.db,payload,'2026-11-09T14:37:00.000001Z',revision_of=7,revision_evidence='one microsecond too late')
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:36:00Z'})
        self.assertEqual(s['candle']['close'],1);self.assertEqual(s['knowledge']['receipt_cutoff'],7)
        paper.start_replay(self.db,account_id='replay-late-start',symbol='AAPL',start='2026-11-09T14:30:00Z',end='2026-11-09T14:40:00Z',snapshot_cutoff=7,step=7)
        s=decisions.create_snapshot(self.db,{'account_id':'replay-late-start','candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertFalse(s['complete']);self.assertTrue(any('did not exist' in r for r in s['reasons']))

    def test_provider_wire_contract_and_controlled_timeout(self):
        request=decisions.provider_request(self.snapshot)
        self.assertEqual(request['model'],'gpt-6-luna')
        self.assertEqual([c['value'] for c in request['questions'][0]['choices']],list(decisions.ACTIONS))
        self.assertEqual(json.loads(request['input'])['snapshot_id'],self.snapshot['snapshot_id'])
        with patch.dict(os.environ,{'OPENAI_API_KEY':'controlled-not-a-real-key'}), patch('urllib.request.urlopen',side_effect=TimeoutError) as call:
            r=decisions.decide(self.db,{'snapshot_id':self.snapshot['snapshot_id']})
        self.assertEqual(r['status'],'timeout')
        self.assertEqual(call.call_args.args[0].full_url,'https://api.openai.com/v1/decisions')
        self.assertEqual(call.call_args.args[0].method,'POST')
        self.assertEqual(call.call_args.kwargs['timeout'],30)
    def test_config_validation_and_missing_account(self):
        with patch.dict(os.environ,{'MARKET_PAPER_ORDER_SIZE':'0'}):
            s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:34:00Z'})
        self.assertFalse(s['complete']);self.assertFalse(s['order_eligible'])
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:34:00Z','account_id':'missing'})
        self.assertFalse(s['complete']);self.assertIsNone(s['account'])
    def test_http_routes_without_extra_test_dependency(self):
        from backend.main import app
        async def request(method,path,body=None):
            sent=[];data=json.dumps(body or {}).encode()
            async def receive():return {'type':'http.request','body':data,'more_body':False}
            async def send(message):sent.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
                'path':path,'raw_path':path.encode(),'query_string':b'', 'root_path':'','scheme':'http',
                'headers':[(b'content-type',b'application/json')],'server':('127.0.0.1',8000),'client':('127.0.0.1',1)},receive,send)
            return sent[0]['status'],json.loads(b''.join(x.get('body',b'') for x in sent[1:]))
        with patch.dict(os.environ,{'MARKET_DB_PATH':str(self.path),'OPENAI_API_KEY':'controlled-not-real'}),patch('backend.decisions.openai_request',side_effect=lambda payload: {'answers':[{'name':'review_verdict','type':'choice','choice':'accept'}]} if payload['questions'][0]['name']=='review_verdict' else answer('wait')):
            status,s=asyncio.run(request('POST','/api/decision-snapshots',{'candle_timestamp':'2026-11-09T14:34:00Z'}))
            self.assertEqual(status,201)
            status,r=asyncio.run(request('POST','/api/decisions',{'snapshot_id':s['snapshot_id']}))
            self.assertEqual(status,200);self.assertEqual(r['status'],'valid')
            self.assertEqual(asyncio.run(request('GET','/api/decisions/'+r['decision_id']))[1],r)
            self.assertEqual(asyncio.run(request('GET','/api/decision-snapshots/'+s['snapshot_id']))[1],s)
            self.assertEqual(asyncio.run(request('POST','/api/decisions',{}))[1]['status'],'missing_input')
