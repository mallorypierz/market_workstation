"""Compare a browser capture with mock input/SQLite; optionally make one live image call."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request
from backend import decisions,chart_analysis
from backend.decision_check import ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',required=True)
    parser.add_argument('--live-db',help='Prepared disposable database served by key-bearing backend on localhost8001')
    parser.add_argument('--png-output',required=True)
    args=parser.parse_args()
    source=sqlite3.connect('file:'+str(Path(args.source_db).resolve())+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    row=source.execute("SELECT * FROM decisions WHERE status='valid' ORDER BY created_at DESC LIMIT 1").fetchone()
    if row is None:parser.error('No valid browser analysis yet; complete the UI operation first')
    result=json.loads(row['result_json']);image=source.execute('SELECT * FROM decision_images WHERE decision_id=?',(row['id'],)).fetchone()
    saved=source.execute('SELECT * FROM decision_snapshots WHERE id=?',(row['snapshot_id'],)).fetchone()
    snapshot=decisions.get_snapshot(source,row['snapshot_id']);raw=bytes(image['png'])
    data_url='data:image/png;base64,'+base64.b64encode(raw).decode()
    decoded=chart_analysis.decode_png(data_url)
    assert decoded[3]=={'snapshot_id':snapshot['snapshot_id'],'sha256':snapshot['sha256'],'chart_range':snapshot['capture_range']}
    call=source.execute('SELECT * FROM chart_provider_calls WHERE snapshot_id=? ORDER BY id DESC LIMIT 1',(snapshot['snapshot_id'],)).fetchone()
    request=json.loads(call['request_json']);provider_raw=base64.b64decode(request['input'][0]['content'][1]['image_url'].split(',')[1])
    assert provider_raw==raw and call['png_sha256']==image['sha256']==hashlib.sha256(raw).hexdigest()
    assert request['input'][0]['content'][0]['data']==snapshot
    orders=source.execute('SELECT count(*) FROM paper_orders').fetchone()[0];assert orders==0
    Path(args.png_output).write_bytes(raw)
    evidence={'source_database':args.source_db,'mock_result':result,'png_sha256':image['sha256'],
        'decoded_dimensions':[decoded[1],decoded[2]],'provider_png_equals_saved':True,'provider_snapshot_equals_saved':True,
        'order_count':orders,'browser_observation':'Student-operated UI; automated browser blocked by approval usage limit.'}
    if args.live_db:
        if snapshot['kind']!='test':parser.error('This verification only transfers explicitly labeled test snapshots')
        target=sqlite3.connect(args.live_db);target.row_factory=sqlite3.Row
        decisions.initialize(target)
        before=ledger(target)
        # Preserve the EXACT immutable record/digest and exported PNG; do not recapture
        # or rewrite metadata. This is fixture import only, never the application path.
        target.execute('INSERT OR IGNORE INTO decision_snapshots VALUES(?,?,?,?)',tuple(saved));target.commit()
        assert decisions.get_snapshot(target,snapshot['snapshot_id'])==snapshot
        body={'analysis':'chart','snapshot_id':snapshot['snapshot_id'],'snapshot_sha256':snapshot['sha256'],
              'chart_range':snapshot['capture_range'],'image':data_url}
        req=urllib.request.Request('http://127.0.0.1:8001/api/decisions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=75) as response:live=json.load(response)
        assert decisions.get_decision(target,live['decision_id'])==live
        stored=target.execute('SELECT png FROM decision_images WHERE decision_id=?',(live['decision_id'],)).fetchone()
        assert bytes(stored[0])==raw and ledger(target)==before
        evidence.update(live_result=live,live_database=args.live_db,live_sqlite_matches_response=True,live_paper_ledger_unchanged=True)
        target.close()
    print(json.dumps(evidence,indent=2))
    source.close()

if __name__=='__main__':main()
