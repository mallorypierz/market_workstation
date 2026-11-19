"""Independent test oracle: SQLite integer window sums, not production SMA code.

Fixed synthetic whole-price fixture, authored for Part 4.2; not market data.
SQL SUM/COUNT windows establish means. Cross-products compare them exactly.
"""
import sqlite3

LONG_CLOSES = [10, 10, 10, 10, 10, 13, 16, 19, 16, 13, 10, 7,
               4, 7, 10, 13, 16, 19, 22, 19, 16, 13, 10, 7,
               10, 13, 16, 19, 16, 13]


def reference(candles, status, short=2, long=3):
    """Oracle accepts integer closes only; deliberately separate from Fraction code."""
    ordered = sorted(candles, key=lambda c: c['timestamp'])
    complete = [c for c in ordered if status[c['timestamp']]['complete']]
    assert all(type(c['close']) is int for c in complete)
    assert type(short) is int and type(long) is int and 0 < short < long
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE closes (seq INTEGER PRIMARY KEY, stamp TEXT, price INTEGER)')
        db.executemany('INSERT INTO closes VALUES (?,?,?)',
                       [(i, c['timestamp'], c['close']) for i, c in enumerate(complete)])
        rows = db.execute(f'''SELECT stamp,
            SUM(price) OVER (ORDER BY seq ROWS {short-1} PRECEDING),
            COUNT(*) OVER (ORDER BY seq ROWS {short-1} PRECEDING),
            SUM(price) OVER (ORDER BY seq ROWS {long-1} PRECEDING),
            COUNT(*) OVER (ORDER BY seq ROWS {long-1} PRECEDING)
            FROM closes ORDER BY seq''').fetchall()
    output, comparisons = {}, []
    for stamp, a, ac, b, bc in rows:
        difference = a * long - b * short if bc == long else 0
        previous = next((x for x in reversed(comparisons) if x != 0), 0)
        signal = ('up' if difference > 0 else 'down') if difference * previous < 0 else None
        comparisons.append(difference)
        output[stamp] = {'timestamp': stamp, 'short': a/short if ac == short else None,
                         'long': b/long if bc == long else None, 'signal': signal}
    return [output.get(c['timestamp'], {'timestamp': c['timestamp'], 'short': None,
                                      'long': None, 'signal': None}) for c in ordered]
