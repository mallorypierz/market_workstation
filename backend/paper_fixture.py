"""Explicit disposable paper-account fixture. Never writes the default market database."""
import argparse
import json
from pathlib import Path
import tempfile
from backend.recorder import connect, record
from backend import paper


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','price','snapshot'])
    parser.add_argument('--database');parser.add_argument('--price',type=float)
    args=parser.parse_args()
    path=Path(tempfile.mkdtemp(prefix='paper-fixture-'))/'account.sqlite3' if args.command=='init' else Path(args.database or '')
    if not path.is_absolute() or not path.parent.name.startswith('paper-fixture-'):
        parser.error('Use the absolute disposable path printed by init')
    db=connect(path);paper.initialize(db)
    try:
        if args.command=='price':
            if paper.price_cents(args.price) is None:parser.error('Supply a positive finite --price')
            stamp=paper.now()
            from datetime import datetime
            stored=record(db,{'id':'AAPL','price':args.price,'time':str(int(datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()*1000)),
                              'test_data':'CONSTRUCTED PAPER PRICE'},stamp,source='yahoo')
            paper.process_live(db)
            print(json.dumps({'constructed_price':args.price,'stored':stored}))
        print(json.dumps({'database':str(path),'label':'CONSTRUCTED PAPER ACCOUNT, NOT REAL TRADING',**paper.snapshot(db)},indent=2))
    finally:db.close()

if __name__=='__main__':main()
