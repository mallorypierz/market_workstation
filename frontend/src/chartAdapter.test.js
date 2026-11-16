import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chartRows, utcLabel } from './chartAdapter.js'

const sample = [
  { timestamp: '2026-11-09T14:31:00Z', open: 102, high: 104, low: 100, close: 101, volume: 850 },
  { timestamp: '2026-11-09T14:30:00Z', open: 100, high: 103, low: 99, close: 102, volume: 1200 },
]

test('intraday conversion preserves distinct UTC minutes and own-open colors', () => {
  const rows = chartRows(sample)
  assert.equal(rows[1].time - rows[0].time, 60)
  assert.equal(utcLabel(rows[1].time), '2026-11-09 14:31 UTC')
  assert.equal(rows[1].close, 101)
  assert.equal(rows[1].volume, 850)
  assert.equal(rows[1].color, '#c34252')
  assert.equal(rows[0].color, '#087f70')
})

test('rejects duplicate timestamps and invalid time rather than collapsing candles', () => {
  assert.throws(() => chartRows([sample[0], sample[0]]), /Duplicate/)
  assert.throws(() => chartRows([{ ...sample[0], timestamp: 'invalid' }]), /Invalid/)
})

test('unknown volume stays null rather than becoming a known zero', () => {
  assert.equal(chartRows([{ ...sample[0], volume: null }])[0].volume, null)
  assert.equal(chartRows([{ ...sample[0], volume: 0 }])[0].volume, 0)
})
