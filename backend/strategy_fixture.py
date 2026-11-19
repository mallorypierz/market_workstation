"""Append a constructed quote only to an explicitly disposable strategy fixture."""
import argparse
from pathlib import Path
import tempfile
from backend.recorder import connect
from backend.test_strategy import quote

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--minute',type=int,required=True)
    parser.add_argument('--price',type=int,required=True);parser.add_argument('--forming',action='store_true');args=parser.parse_args()
    path=Path(args.database).resolve()
    if not path.parent.name.startswith('strategy-browser-') or not any(path.is_relative_to(p) for p in [Path(tempfile.gettempdir()).resolve(),Path('/private/tmp')]):
        parser.error('Only a disposable strategy-browser-* database is allowed')
    db=connect(path);quote(db,args.minute,args.price,not args.forming);db.close()
