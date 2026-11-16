"""Named chart settings, isolated from immutable market-session storage."""
import json
import os
from pathlib import Path
import sqlite3
from backend.recorder import ROOT
from backend.indicators import REGISTRY, window_settings, calculate
from backend.timeframes import TIMEFRAMES


def settings_path():
    path = Path(os.environ.get('MARKET_SETTINGS_DB_PATH', 'backend/data/chart-settings.sqlite3')).expanduser()
    return path if path.is_absolute() else ROOT / path


def validate_chart(symbol, source, timeframe):
    if (symbol, source) not in {('AAPL','yahoo'),('SAMPLE','sample')} or timeframe not in TIMEFRAMES:
        raise ValueError('Unsupported chart symbol, source or timeframe')


def list_instances(symbol, source, timeframe):
    validate_chart(symbol, source, timeframe)
    path = settings_path()
    if not path.exists(): return []
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute('SELECT id, name, type, settings_json FROM indicator_instances WHERE symbol=? AND source=? AND timeframe=? ORDER BY id', (symbol,source,timeframe)).fetchall()
        return [{'id':r['id'],'name':r['name'],'type':r['type'],'settings':json.loads(r['settings_json'])} for r in rows]
    finally: db.close()


def add_instance(symbol, source, timeframe, name, kind, settings):
    validate_chart(symbol, source, timeframe)
    if kind not in REGISTRY: raise ValueError('Unknown indicator type')
    settings = window_settings(settings)
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Name must contain 1 to 80 characters')
    name = name.strip()
    path = settings_path(); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS indicator_instances (
                id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, source TEXT NOT NULL,
                timeframe TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
                settings_json TEXT NOT NULL, UNIQUE(symbol,source,timeframe,name))''')
            cursor = db.execute('INSERT INTO indicator_instances(symbol,source,timeframe,name,type,settings_json) VALUES(?,?,?,?,?,?)',
                                (symbol,source,timeframe,name,kind,json.dumps(settings,sort_keys=True)))
            return {'id':cursor.lastrowid,'name':name,'type':kind,'settings':settings}
    except sqlite3.IntegrityError as error:
        raise ValueError('An indicator with that name already exists on this chart') from error
    finally: db.close()


def with_indicators(view):
    source = 'sample' if view['symbol']=='SAMPLE' else 'yahoo'
    instances = list_instances(view['symbol'],source,view['timeframe'])
    return {**view, 'indicators': [{**item, 'units':REGISTRY[item['type']].units,
            'pane':REGISTRY[item['type']].pane,
            'values':calculate(item['type'],view['candles'],view['status'],item['settings'])} for item in instances]}


def update_window(identity, settings):
    settings = window_settings(settings)
    path = settings_path()
    if not path.exists(): raise ValueError('Unknown indicator')
    with sqlite3.connect(path) as db:
        cursor = db.execute('UPDATE indicator_instances SET settings_json=? WHERE id=?',
                            (json.dumps(settings, sort_keys=True), identity))
        if not cursor.rowcount: raise ValueError('Unknown indicator')
    return {'id': identity, 'settings': settings}
