"""Save/inspect three controlled review cases, or one live two-role example."""
import argparse
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import urllib.request
from backend import decisions,decision_review
from backend.decision_fixture import build
from backend.recorder import connect
from backend.decision_check import ledger


def http(path,body):
    req=urllib.request.Request('http://127.0.0.1:8001'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=75) as response:return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--database')
    args=parser.parse_args()
    if args.live and not args.database:parser.error('--live requires the prepared disposable backend database')
    path=Path(args.database) if args.database else Path(tempfile.mkdtemp(prefix='review-check-'))/'fixture.sqlite3'
    if not args.live and path.exists():parser.error('Offline checks require a new disposable database')
    if args.live and not path.exists():parser.error('Prepared live-check database is missing')
    db=connect(path)
    try:
        s=http('/api/decision-snapshots',{'candle_timestamp':'2026-11-09T14:34:00Z'}) if args.live else build(db)
        before=ledger(db);results=[]
        if args.live:
            r=http('/api/decisions',{'snapshot_id':s['snapshot_id']})
            assert set(r.get('roles',{}))=={'analyst','reviewer'},'Backend must be restarted with the review code'
            results.append({'case':'live_two_role_example','snapshot':s,'result':r})
        else:
            for name,cash,verdict in [('agreed_policy_eligible',100000,'accept'),('reviewer_rejection',100000,'reject_unsupported_signal'),('unaffordable_buy_both_accept',100,'accept')]:
                current=copy.deepcopy(s);current['account'].update(cash_cents=cash,cash=cash/100)
                current=decisions.save_snapshot(db,current);calls=[]
                def provider(payload):
                    calls.append(payload)
                    q=payload['questions'][0]['name']
                    return {'answers':[{'name':q,'type':'choice','choice':'buy' if q=='paper_action' else verdict}]}
                r=decision_review.run(db,{'snapshot_id':current['snapshot_id']},provider)
                assert len(calls)==2
                assert json.loads(calls[0]['input'])==calls[1]['input'][0]['content'][0]['data']['snapshot']==current
                assert calls[1]['input'][0]['content'][0]['data']['analyst']['proposal']==r['proposal']
                results.append({'case':name,'snapshot':current,'result':r,'same_snapshot_sent_to_both':True})
            assert [v['result']['status'] for v in results]==['valid','review_rejected','blocked_by_rules']
            assert [v['result']['final_check']['passed'] for v in results]==[True,False,False]
        for item in results:
            r=item['result'];saved=decisions.get_decision(db,r['decision_id'])
            assert saved==r
            assert decisions.get_snapshot(db,r['snapshot_id'])==item['snapshot']
            assert r['roles']['analyst']['snapshot_sha256']==r['roles']['reviewer']['snapshot_sha256']==item['snapshot']['sha256']
        assert ledger(db)==before
        print(json.dumps({'database':str(path),'market_data':'CONSTRUCTED test records; no live market verification',
            'cases':results,'sqlite_matches_responses':True,'paper_ledger_unchanged':True,
            'note':'All complete test snapshots remain execution-ineligible. The agreed case passes account/strategy/review policy.'},indent=2))
    finally:db.close()

if __name__=='__main__':main()
