// Intraday Lightweight Charts times are Unix seconds, shared by both panes.
export function chartRows(rows) {
  if (!Array.isArray(rows)) throw new Error('History must be an array')
  const result = rows.map(row => {
    const time = Date.parse(row.timestamp) / 1000
    if (!Number.isFinite(time) || time % 60 !== 0 || !row.timestamp.endsWith('Z') ||
        !['open', 'high', 'low', 'close'].every(key => Number.isFinite(row[key])) ||
        !(row.volume === null || Number.isFinite(row.volume))) {
      throw new Error('Invalid one-minute candle')
    }
    return { ...row, time, color: row.close >= row.open ? '#087f70' : '#c34252' }
  }).sort((a, b) => a.time - b.time)
  if (result.some((row, i) => i > 0 && row.time === result[i - 1].time)) {
    throw new Error('Duplicate candle timestamp')
  }
  return result
}

export const utcLabel = time => new Date(time * 1000).toISOString().replace('T', ' ').replace(':00.000Z', ' UTC')
