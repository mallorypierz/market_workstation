"""Completed-candle SMA; exact rational comparison before JSON/display rounding."""
from backend.indicators import exact_values
import os


def validate_windows(short, long):
    if type(short) is not int or type(long) is not int or not 0 < short < long:
        raise ValueError('SMA windows must be positive whole numbers with short < long')


def sma(candles, status, short=2, long=3):
    validate_windows(short, long)
    short_rows = exact_values('sma', candles, status, {'window': short})
    long_rows = exact_values('sma', candles, status, {'window': long})
    result, side = [], None
    for left, right in zip(short_rows, long_rows):
        a, b, signal = left['value'], right['value'], None
        if a is not None and b is not None and a != b:
            new_side = 'above' if a > b else 'below'
            if side is not None and side != new_side:
                signal = 'up' if new_side == 'above' else 'down'
            side = new_side
        result.append({'timestamp': left['timestamp'], 'short': float(a) if a is not None else None,
                       'long': float(b) if b is not None else None, 'signal': signal})
    return {'short_window': short, 'long_window': long, 'values': result}


def with_sma(view, short=2, long=3):
    return {**view, 'sma': sma(view['candles'], view['status'], short, long),
            'data_label': os.environ.get('MARKET_DATA_LABEL', '')}
