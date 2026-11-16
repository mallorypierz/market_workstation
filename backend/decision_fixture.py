"""Constructed seven-close decision fixture, isolated from actual captures."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

from backend import decisions, paper
from backend.recorder import connect, record


def build(db):
    with patch('backend.paper.now', return_value='2026-11-09T14:29:00Z'):
        paper.initialize(db)
    base = datetime(2026,11,9,14,30,tzinfo=timezone.utc)
    for index, price in enumerate([13,10,7,13,19,7,1]):
        stamp = base + timedelta(minutes=index,seconds=50)
        record(db, {'id':'AAPL','price':price,'time':str(int(stamp.timestamp()*1000)),
                    'test_data':'CONSTRUCTED DECISION FIXTURE'}, stamp.isoformat())
    decisions.initialize(db)
    return decisions.create_snapshot(db, {'candle_timestamp':'2026-11-09T14:34:00Z'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    args=parser.parse_args()
    path=Path(args.database)
    if path.exists(): parser.error('Use a new disposable database; refusing to replace an existing file')
    db=connect(path)
    try:
        snapshot=build(db)
        print(json.dumps({'database':str(path),'snapshot_id':snapshot['snapshot_id'],
                          'complete':snapshot['complete'],'market_data':snapshot['market_data'],
                          'indicators':snapshot['indicators'],'account':snapshot['account']},indent=2))
    finally: db.close()

if __name__=='__main__': main()
