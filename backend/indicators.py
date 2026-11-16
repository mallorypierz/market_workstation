"""Indicator registry: validated settings + completed candles -> timestamped values."""
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable


def window_settings(settings):
    if not isinstance(settings, dict) or set(settings) != {'window'}:
        raise ValueError('Settings must contain only window')
    if type(settings['window']) is not int or settings['window'] < 1:
        raise ValueError('Window must be a positive whole number (at least 1)')
    return dict(settings)


def mean_close(rows):
    return sum(Fraction(str(row['close'])) for row in rows) / len(rows)


def price_range(rows):
    return max(Fraction(str(row['high'])) for row in rows) - min(Fraction(str(row['low'])) for row in rows)


@dataclass(frozen=True)
class IndicatorType:
    label: str
    inputs: tuple
    units: str
    pane: str
    reduce: Callable


# Add another completed-candle rolling scalar calculation here; Vue discovers metadata.
REGISTRY = {
    'sma': IndicatorType('Simple moving average', ('close',), 'price units', 'price', mean_close),
    'rolling_range': IndicatorType('Rolling price range', ('high', 'low'), 'price units (difference)', 'separate', price_range),
}


def catalog():
    return [{'type': key, 'label': item.label, 'inputs': list(item.inputs), 'units': item.units,
             'pane': item.pane, 'settings': {'window': {'type': 'integer', 'minimum': 1, 'default': 2}},
             'completion': 'complete candles only', 'output': 'one value or null per candle timestamp'}
            for key, item in REGISTRY.items()]


def exact_values(kind, candles, status, settings):
    if kind not in REGISTRY:
        raise ValueError('Unknown indicator type')
    window = window_settings(settings)['window']
    completed, output = [], []
    for row in sorted(candles, key=lambda c: c['timestamp']):
        value = None
        if status.get(row['timestamp'], {}).get('complete', False):
            completed.append(row)
            if len(completed) >= window:
                value = REGISTRY[kind].reduce(completed[-window:])
        output.append({'timestamp': row['timestamp'], 'value': value})
    return output


def calculate(kind, candles, status, settings):
    return [{**row, 'value': None if row['value'] is None else float(row['value'])}
            for row in exact_values(kind, candles, status, settings)]
