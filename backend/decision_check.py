"""Repeatable isolated decision check; --live makes exactly one provider-backed request."""
import argparse
import json
from pathlib import Path
import tempfile
import urllib.request

from backend import decisions
from backend.decision_fixture import build
from backend.recorder import connect


def ledger(db):
    tables=['paper_accounts','paper_positions','paper_orders','paper_fills','paper_requests','paper_pnl']
    return {name:[dict(r) for r in db.execute('SELECT * FROM '+name)] for name in tables}


def http(method, path, body=None):
    request=urllib.request.Request('http://127.0.0.1:8001'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(request,timeout=75) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='One real request to the backend already running on localhost8001')
    parser.add_argument('--database',help='Same disposable database as the backend; required for --live')
    args=parser.parse_args()
    if args.live and not args.database:parser.error('--live requires --database')
    path=Path(args.database) if args.database else Path(tempfile.mkdtemp(prefix='decision-check-'))/'fixture.sqlite3'
    if args.live and not path.exists():parser.error('Live check requires the prepared fixture database')
    db=connect(path)
    try:
        if args.live:
            snapshot=http('POST','/api/decision-snapshots',{'candle_timestamp':'2026-11-09T14:34:00Z'})
        else:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_accounts'").fetchone():
                parser.error('Offline check requires a new disposable database')
            snapshot=build(db)
        if snapshot.get('kind')!='test' or not snapshot.get('complete'):
            raise RuntimeError('Check requires a complete, explicitly labeled test snapshot')
        before=ledger(db)
        if args.live:
            result=http('POST','/api/decisions',{'snapshot_id':snapshot['snapshot_id']})
            fetched=http('GET','/api/decisions/'+result['decision_id'])
            assert fetched==result
            failure=None
        else:
            def timeout(_):raise TimeoutError('constructed timeout')
            result=decisions.decide(db,{'snapshot_id':snapshot['snapshot_id']},
                lambda _: {'answers':[{'name':'paper_action','type':'choice','choice':'wait'}]})
            failure=decisions.decide(db,{'snapshot_id':snapshot['snapshot_id']},timeout)
            assert result['status']=='valid' and failure['status']=='timeout'
        stored=decisions.get_decision(db,result['decision_id'])
        assert result==stored
        assert decisions.get_snapshot(db,snapshot['snapshot_id'])==snapshot
        assert ledger(db)==before
        evidence={'database':str(path),'snapshot_id':snapshot['snapshot_id'],'snapshot_sha256':snapshot['sha256'],
            'market_data':snapshot['market_data'],'facts':{'candle':snapshot['candle'],'indicators':snapshot['indicators'],'account':snapshot['account']},
            'result':result,'controlled_failure':failure,'sqlite_matches_response':True,'paper_ledger_unchanged':True}
        print(json.dumps(evidence,indent=2))
        if args.live and result['model_call']!='live_provider':raise SystemExit(2)
    finally:db.close()

if __name__=='__main__':main()
