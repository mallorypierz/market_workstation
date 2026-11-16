import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import decisions,decision_review
from backend.decision_fixture import build
from backend.recorder import connect
from backend.decision_check import ledger
from backend.test_chart_analysis import png


def choice(name,value):return {'answers':[{'name':name,'type':'choice','choice':value}]}

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'review.sqlite3'
        self.db=connect(self.path);self.snapshot=build(self.db)
    def tearDown(self):self.db.close();self.folder.cleanup()
    def run_case(self,verdict='accept',cash=100000,application=False):
        s=copy.deepcopy(self.snapshot);s['account'].update(cash_cents=cash,cash=cash/100)
        # Isolated test of the application eligibility branch; never expose this override via HTTP.
        if application:s.update(kind='application',order_eligible=True,market_data='CONSTRUCTED eligibility branch UNIT TEST')
        s=decisions.save_snapshot(self.db,s);calls=[];before=ledger(self.db)
        def provider(payload):
            calls.append(payload)
            return choice('paper_action','buy') if len(calls)==1 else choice('review_verdict',verdict)
        result=decision_review.run(self.db,{'snapshot_id':s['snapshot_id']},provider)
        self.assertEqual(ledger(self.db),before)
        self.assertEqual(decisions.get_decision(self.db,result['decision_id']),result)
        return result,calls,s
    def test_three_required_cases(self):
        good,calls,s=self.run_case(application=True)
        self.assertTrue(good['order_eligible']);self.assertTrue(good['final_check']['passed']);self.assertEqual(good['status'],'valid')
        self.assertEqual(len(calls),2)
        analyst_snapshot=json.loads(calls[0]['input']);review=calls[1]['input'][0]['content'][0]['data']
        self.assertEqual(analyst_snapshot,s);self.assertEqual(review['snapshot'],s)
        self.assertEqual(review['analyst']['proposal'],{'action':'buy','quantity':1})
        self.assertEqual(good['roles']['analyst']['snapshot_sha256'],good['roles']['reviewer']['snapshot_sha256'])
        rejected,_,_=self.run_case('reject_unsupported_signal',application=True)
        self.assertEqual(rejected['status'],'review_rejected');self.assertFalse(rejected['order_eligible'])
        poor,_,_=self.run_case(cash=100,application=True)
        self.assertEqual(poor['roles']['reviewer']['verdict'],'accept');self.assertEqual(poor['proposal']['action'],'buy')
        self.assertEqual(poor['status'],'blocked_by_rules');self.assertFalse(poor['final_check']['account_rules_pass'])
        self.assertEqual(poor['final_check']['buy_cost_cents'],1900);self.assertFalse(poor['order_eligible'])
    def test_strategy_enforced_even_with_approval(self):
        s=copy.deepcopy(self.snapshot);s['indicators']['at_candle']['signal']='down'
        s=decisions.save_snapshot(self.db,s)
        result=decision_review.run(self.db,{'snapshot_id':s['snapshot_id']},lambda p:choice('review_verdict','accept') if p['questions'][0]['name']=='review_verdict' else choice('paper_action','buy'))
        self.assertEqual(result['status'],'blocked_by_rules');self.assertFalse(result['final_check']['strategy_rules_pass'])
    def test_analyst_failure_skips_reviewer_and_reviewer_failure_saved(self):
        calls=[]
        def bad(p):calls.append(p);return {'answers':[]}
        r=decision_review.run(self.db,{'snapshot_id':self.snapshot['snapshot_id']},bad)
        self.assertEqual(len(calls),1);self.assertEqual(r['roles']['reviewer']['call_count'],0);self.assertFalse(r['order_eligible'])
        for response,status in [(choice('wrong','accept'),'review_malformed_answer'),(choice('review_verdict','unexpected'),'review_malformed_answer'),(choice('review_verdict',float('nan')),'review_malformed_answer'),({'answers':[{'name':'review_verdict','type':'refusal'}]},'review_refused')]:
            r=decision_review.run(self.db,{'snapshot_id':self.snapshot['snapshot_id']},lambda p:response if p['questions'][0]['name']=='review_verdict' else choice('paper_action','buy'))
            self.assertEqual(r['status'],status);self.assertFalse(r['order_eligible'])
    def test_timeouts_one_call_each_and_late_results_cannot_overwrite(self):
        def slow(p):
            if p['questions'][0]['name']=='review_verdict':time.sleep(.1);return choice('review_verdict','accept')
            return choice('paper_action','buy')
        with patch('backend.decision_review.ROLE_TIMEOUT_SECONDS',.01):
            r=decision_review.run(self.db,{'snapshot_id':self.snapshot['snapshot_id']},slow)
        self.assertEqual(r['status'],'review_timeout');self.assertEqual([v['call_count'] for v in r['roles'].values()],[1,1])
        time.sleep(.12)
        self.assertEqual(decisions.get_decision(self.db,r['decision_id']),r)
        def timeout(p):raise TimeoutError('Do not persist this secret-like detail')
        r=decision_review.run(self.db,{'snapshot_id':self.snapshot['snapshot_id']},timeout)
        self.assertEqual(r['status'],'timeout');self.assertEqual(r['roles']['reviewer']['call_count'],0)
        self.assertNotIn('secret-like',json.dumps(r))
    def test_same_png_and_named_answers_reach_reviewer(self):
        s=self.snapshot;image=png(s);calls=[]
        def provider(p):
            calls.append(p)
            return choice('review_verdict','accept') if len(calls)==2 else {'answers':[{'name':n,'type':'choice','choice':v} for n,v in [('action','buy'),('crossover','up'),('evidence','sufficient')]]}
        r=decision_review.run(self.db,{'analysis':'chart','snapshot_id':s['snapshot_id'],'snapshot_sha256':s['sha256'],'chart_range':s['capture_range'],'image':image},provider)
        self.assertEqual(r['status'],'valid');self.assertEqual(len(calls),2)
        a,b=[p['input'][0]['content'] for p in calls]
        self.assertEqual(a[1],b[1]);self.assertEqual(b[0]['data']['snapshot'],a[0]['data'])
        self.assertEqual(b[0]['data']['analyst']['named_answers'],r['answers'])
        self.assertFalse(r['order_eligible']) # Test provenance survives both acceptances.
    def test_no_provisional_eligibility_and_restart_persistence(self):
        calls=[]
        def provider(payload):
            calls.append(payload)
            if len(calls)==2:
                reader=connect(self.path)
                try:
                    row=reader.execute('SELECT result_json FROM decisions ORDER BY created_at DESC LIMIT 1').fetchone()
                    pending=json.loads(row[0]);self.assertEqual(pending['status'],'review_pending');self.assertFalse(pending['order_eligible'])
                    self.assertEqual(pending['roles']['analyst']['output'][0]['choice'],'buy')
                finally:reader.close()
                return choice('review_verdict','accept')
            return choice('paper_action','buy')
        r=decision_review.run(self.db,{'snapshot_id':self.snapshot['snapshot_id']},provider)
        self.assertEqual(r['status'],'valid')
        self.db.close();self.db=connect(self.path)
        self.assertEqual(decisions.get_decision(self.db,r['decision_id']),r)
