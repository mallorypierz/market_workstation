<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { createChart, CandlestickSeries, HistogramSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts'
import { chartRows, utcLabel } from './chartAdapter.js'
import PaperAccount from './PaperAccount.vue'
import AskChart from './AskChart.vue'
import PaperAutomation from './PaperAutomation.vue'
const paperComponent = ref(null)
function freezeRequest() {
  if (source.value !== 'yahoo' || !selectedStatus.value?.complete) throw new Error('Choose a completed AAPL candle with full coverage.')
  const visible = chart.timeScale().getVisibleRange()
  const first = rows.value.find(r => !visible || r.time >= visible.from)
  if (!first || first.time > selected.value.time) throw new Error('Move the selected candle into the visible chart range before capturing.')
  const request = {symbol:symbol.value, interval:timeframe.value, candle_timestamp:selected.value.timestamp,
    short:shortWindow.value,long:longWindow.value,account_id:paperComponent.value?.accountId || '',
    chart_range:{from:first.timestamp,to:selected.value.timestamp}}
  if (mode.value === 'replay') request.receipt_cutoff = feed.value.latest?.receipt_id || 0
  return request
}
const paperView = ref(null)

const indicatorTypes = ref([]), indicatorType = ref('sma'), indicatorName = ref(''), indicatorWindow = ref(2)
const indicatorError = ref(''), savingIndicator = ref(false), instances = ref([])
const indicatorLines = new Map()
const editedWindows = ref({})
async function updateIndicator(item) {
  indicatorError.value = ""
  try {
    const response = await fetch(`/api/indicators/${item.id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({settings:{window:Number(editedWindows.value[item.id] ?? item.settings.window)}})})
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || "Could not update indicator")
    await load()
  } catch(error) { indicatorError.value=error.message }
}
const indicatorDefinition = computed(() => indicatorTypes.value.find(item => item.type === indicatorType.value))
const instanceValue = item => item.values.find(row => row.timestamp === selected.value?.timestamp)?.value
function renderIndicators(items) {
  instances.value = items
  const ids = new Set(items.map(item => item.id))
  for (const [id, line] of indicatorLines) if (!ids.has(id)) { chart.removeSeries(line); indicatorLines.delete(id) }
  const colors = ['#b45309','#0e7490','#be185d','#4d7c0f']
  items.forEach((item, index) => {
    let line = indicatorLines.get(item.id)
    if (!line) {
      line = chart.addSeries(LineSeries, {color: colors[index % colors.length], lineWidth: 2, title: item.name,
        lastValueVisible: false, priceLineVisible: false}, item.pane === 'price' ? 0 : 2)
      indicatorLines.set(item.id,line)
    }
    line.setData(item.values.map(row => ({time: Date.parse(row.timestamp)/1000, ...(row.value == null ? {} : {value: row.value})})))
  })
}
async function addIndicator() {
  indicatorError.value = ''
  const window = Number(indicatorWindow.value)
  if (!Number.isSafeInteger(window) || window < 1) { indicatorError.value = 'Window must be a positive whole number (at least 1).'; return }
  if (!indicatorName.value.trim()) { indicatorError.value = 'Give the indicator a name.'; return }
  savingIndicator.value = true
  try {
    const response = await fetch('/api/indicators', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:symbol.value, source:source.value, timeframe:timeframe.value,
        name:indicatorName.value, type:indicatorType.value, settings:{window}})})
    const body = await response.json()
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Invalid indicator settings')
    indicatorName.value = ''
    await load()
  } catch (error) { indicatorError.value = error.message }
  finally { savingIndicator.value = false }
}
const shortInput = ref(2), longInput = ref(3)
const shortWindow = ref(2), longWindow = ref(3)
const smaError = ref(''), smaValues = ref([]), dataLabel = ref('')
const selectedSma = computed(() => smaValues.value.find(row => row.timestamp === selected.value?.timestamp))
const signals = computed(() => smaValues.value.filter(row => row.signal))
const displaySma = value => value == null ? 'Unavailable' : Number(value.toFixed(6)).toString()
function applyWindows() {
  const a = Number(shortInput.value), b = Number(longInput.value)
  if (!Number.isSafeInteger(a) || !Number.isSafeInteger(b) || a <= 0 || a >= b) {
    smaError.value = 'Use positive whole numbers with short smaller than long.'; return
  }
  smaError.value = ''; shortWindow.value = a; longWindow.value = b; load()
}
const container = ref(null)
const rows = ref([])
const selectedTime = ref(null)
const selectionPinned = ref(false)
const selected = computed(() => rows.value.find(row => row.time === Number(selectedTime.value)))
const mode = ref('live')
const saved = ref([])
const replayStart = ref('')
const replayEnd = ref('')
const replay = ref({step: 0, total: 0, finished: false, snapshot_cutoff: null})
const replayRunning = ref(false)
const symbol = ref('AAPL')
const timeframe = ref('1m')
const source = computed(() => symbol.value === 'AAPL' ? 'yahoo' : 'sample')
const feed = ref({ status: 'connecting', latest: null })
const completion = ref({})
const selectedStatus = computed(() => selected.value ? completion.value[selected.value.timestamp] : null)
const status = ref('Loading backend candles…')
const failed = ref(false)
const loading = ref(false)
const transport = ref('disconnected')
const controlling = ref(false)
const clockTick = ref(Date.now())
const feedReceivedAt = ref(Date.now())
const displayFeedStatus = computed(() => mode.value === 'replay' ? 'Replay' : transport.value === 'connected' ? feed.value.status : 'unknown · backend not connected')
const age = computed(() => mode.value === 'replay' ? 'Not applicable (Replay)' : feed.value.source_age_seconds == null ? 'Unavailable' : `${Math.max(0, feed.value.source_age_seconds + (clockTick.value - feedReceivedAt.value) / 1000).toFixed(1)} seconds`)
let shortLine, longLine, markers
let chart, candles, volume, socket, controller, retryTimer, generation = 0
let fitted = false
let clockTimer

function applyView(view) {
  if (view.symbol !== symbol.value || view.timeframe !== timeframe.value) return
  paperView.value = view
  const data = chartRows(view.candles)
  const followLatest = selectedTime.value == null || (!selectionPinned.value && selectedTime.value === rows.value.at(-1)?.time)
  rows.value = data
  completion.value = view.status
  renderIndicators(view.indicators || [])
  smaValues.value = view.sma?.values || []
  dataLabel.value = view.data_label || ''
  for (const [key, line] of [['short', shortLine], ['long', longLine]]) {
    line.setData(smaValues.value.map(row => ({time: Date.parse(row.timestamp) / 1000, ...(row[key] == null ? {} : {value: row[key]})})))
  }
  shortLine.applyOptions({title: `Short SMA (${shortWindow.value})`})
  longLine.applyOptions({title: `Long SMA (${longWindow.value})`})
  markers.setMarkers(signals.value.map(row => ({time: Date.parse(row.timestamp) / 1000,
    position: row.signal === 'up' ? 'belowBar' : 'aboveBar', color: row.signal === 'up' ? '#087f70' : '#c34252',
    shape: row.signal === 'up' ? 'arrowUp' : 'arrowDown', text: `SMA ${row.signal}`})))
  if (view.feed) { feed.value = view.feed; feedReceivedAt.value = Date.now() }
  candles.setData(data.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })))
  // Whitespace at unknown-volume times; never fabricate a zero-height known-volume bar.
  volume.setData(data.map(({ time, volume: value, color }) => value == null ? { time } : { time, value, color }))
  if (followLatest || !data.some(row => row.time === selectedTime.value)) selectedTime.value = data.at(-1)?.time ?? null
  status.value = data.length ? `${data.length} ${timeframe.value} candles · UTC · regular session` : 'No regular-session candles available. No sample data substituted.'
  failed.value = false
  if (!fitted && data.length) { chart.timeScale().fitContent(); fitted = true }
}

function openStream(token, query) {
  if (token !== generation) return
  transport.value = 'connecting'
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/stream?${query}`)
  socket = ws
  ws.onopen = () => { if (token === generation) transport.value = 'connected' }
  ws.onmessage = event => {
    if (token !== generation) return
    try { applyView(JSON.parse(event.data)); loading.value = false }
    catch { status.value = 'Invalid candle message'; failed.value = true }
  }
  ws.onclose = () => {
    if (token !== generation) return
    transport.value = 'disconnected'
    loading.value = false
    status.value = 'Backend connection lost. Displayed candles are stored values; reconnecting…'
    retryTimer = setTimeout(() => openStream(token, query), 2000)
  }
  ws.onerror = () => ws.close()
}

async function load() {
  replayRunning.value = false
  const token = ++generation
  clearTimeout(retryTimer)
  controller?.abort(); socket?.close()
  controller = new AbortController()
  fitted = false
  loading.value = true; failed.value = false
  rows.value = []; selectedTime.value = null; selectionPinned.value = false; completion.value = {}
  renderIndicators([])
  feed.value = { status: source.value === 'sample' ? 'synthetic' : 'connecting', latest: null }
  candles.setData([]); volume.setData([]); shortLine.setData([]); longLine.setData([]); markers.setMarkers([]); smaValues.value = []
  status.value = 'Loading matching backend history…'
  const query = new URLSearchParams({ symbol: symbol.value, source: source.value, timeframe: timeframe.value, short: shortWindow.value, long: longWindow.value })
  chart.applyOptions({ timeScale: { tickMarkFormatter: time => timeframe.value === '1d' ? utcLabel(time).slice(0, 10) : utcLabel(time).slice(11,16) } })
  if (mode.value === 'replay') {
    await fetchReplay(0, true, token)
    return
  }
  try {
    const response = await fetch(`/api/history?${query}&include_metadata=true`, { signal: controller.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const view = await response.json()
    if (token !== generation) return
    applyView(view)
  } catch (error) {
    if (token !== generation) return
    status.value = `History unavailable: ${error.message}`; failed.value = true
  }
  if (token === generation) { loading.value = false; openStream(token, query) }
}

async function fetchReplay(step, reset = false, token = generation) {
  const params = new URLSearchParams({symbol: symbol.value, timeframe: timeframe.value, start: replayStart.value, end: replayEnd.value, step, short: shortWindow.value, long: longWindow.value})
  if (!reset && replay.value.snapshot_cutoff != null) params.set('snapshot_cutoff', replay.value.snapshot_cutoff)
  try {
    const response = await fetch(`/api/replay?${params}`, {signal: controller.signal})
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail || `HTTP ${response.status}`) }
    const view = await response.json()
    if (token !== generation || mode.value !== 'replay') return
    applyView(view)
    replay.value = view.replay
    if (view.replay.finished && rows.value.length) chart.timeScale().fitContent()
    transport.value = 'replay HTTP · no live stream'
    status.value = view.replay.empty ? 'This selection has no recorded observations.' : `Replay ${view.replay.finished ? 'complete' : 'ready'} · ${view.replay.step} / ${view.replay.total} recorded deliveries`
    loading.value = false
  } catch (error) {
    if (token !== generation) return
    replayRunning.value = false; loading.value = false; failed.value = true
    status.value = `Replay unavailable: ${error.message}`
  }
}

async function playReplay() {
  if (replayRunning.value) { replayRunning.value = false; return }
  const token = generation
  if (replay.value.finished) await fetchReplay(0, false, token)
  replayRunning.value = true
  while (replayRunning.value && token === generation && !replay.value.finished) {
    await fetchReplay(replay.value.step + 1, false, token)
    await new Promise(resolve => setTimeout(resolve, 80))
  }
  replayRunning.value = false
}

async function changeMode() {
  replayRunning.value = false
  if (mode.value === 'replay') {
    ++generation; controller?.abort(); socket?.close(); clearTimeout(retryTimer)
    try {
      const stopped = await fetch('/api/feed/disconnect', {method: 'POST'})
      if (!stopped.ok) throw new Error('Could not disconnect Yahoo')
      const response = await fetch('/api/recordings')
      if (!response.ok) throw new Error('Could not list recordings')
      saved.value = await response.json()
      if (!saved.value.length) {
        rows.value=[]; candles.setData([]); volume.setData([]); renderIndicators([])
        status.value = 'No recorded observations are available.'
        replay.value = {step:0,total:0,finished:true,snapshot_cutoff:null}
        transport.value='replay HTTP · no live stream'; feed.value={status:'replay',latest:null}
        return
      }
      symbol.value = saved.value[0].symbol
      replayStart.value = saved.value[0].start; replayEnd.value = saved.value[0].end
    } catch (error) { status.value = error.message; failed.value = true; return }
  }
  await load()
}

function chooseSavedSymbol() {
  const selection = saved.value.find(row => row.symbol === symbol.value)
  if (selection) { replayStart.value = selection.start; replayEnd.value = selection.end }
  load()
}

async function controlFeed() {
  controlling.value = true
  try {
    const action = feed.value.enabled ? 'disconnect' : 'connect'
    const response = await fetch(`/api/feed/${action}`, { method: 'POST' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    feed.value = await response.json()
    feedReceivedAt.value = Date.now()
  } catch (error) { status.value = `Feed control failed: ${error.message}` }
  finally { controlling.value = false }
}

onMounted(async () => {
  clockTimer = setInterval(() => { clockTick.value = Date.now() }, 1000)
  chart = createChart(container.value, {
    autoSize: true,
    layout: { background: { color: '#ffffff' }, textColor: '#354b5e', attributionLogo: true },
    grid: { vertLines: { color: '#eef2f5' }, horzLines: { color: '#eef2f5' } },
    timeScale: { timeVisible: true, secondsVisible: false },
    localization: { timeFormatter: utcLabel },
  })
  candles = chart.addSeries(CandlestickSeries, { upColor: '#087f70', downColor: '#c34252', borderVisible: false, wickUpColor: '#087f70', wickDownColor: '#c34252', title: 'Price' })
  shortLine = chart.addSeries(LineSeries, {color: '#2563eb', lineWidth: 2, lastValueVisible: false, priceLineVisible: false, title: 'Short SMA'})
  longLine = chart.addSeries(LineSeries, {color: '#a855f7', lineWidth: 2, lastValueVisible: false, priceLineVisible: false, title: 'Long SMA'})
  markers = createSeriesMarkers(candles, [])
  volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, title: 'Volume · shares' }, 1)
  chart.panes()[1].setHeight(130)
  chart.subscribeCrosshairMove(event => { if (!selectionPinned.value && event.time !== undefined && event.seriesData.has(candles)) selectedTime.value = event.time })
  try {
    const response = await fetch('/api/indicator-types')
    if (!response.ok) throw new Error('Could not load indicator types')
    indicatorTypes.value = await response.json()
  } catch (error) { indicatorError.value = error.message }
  load()
})

onBeforeUnmount(() => {
  replayRunning.value = false; generation++; clearInterval(clockTimer); clearTimeout(retryTimer); controller?.abort(); socket?.close(); chart?.remove()
})
</script>

<template>
  <section aria-labelledby="chart-title">
    <div class="chart-heading">
      <div><h2 id="chart-title">{{ mode === 'replay' ? 'Replay · ' : '' }}{{ symbol }} · {{ timeframe }} candles</h2>
        <p>{{ mode === 'replay' ? 'Replay · recorded Yahoo observations · live feed disconnected' : source === 'yahoo' ? 'Yahoo Finance · live subscription and stored history' : 'Synthetic CSV sample · not live market data' }}</p></div>
      <button :disabled="loading" @click="load">Reload history</button>
    </div>
    <p v-if="dataLabel" role="note"><strong>{{ dataLabel }}</strong></p>
    <form class="controls" @submit.prevent="applyWindows">
      <label for="short-sma">Short SMA</label><input id="short-sma" type="number" min="1" step="1" v-model="shortInput" required>
      <label for="long-sma">Long SMA</label><input id="long-sma" type="number" min="1" step="1" v-model="longInput" required>
      <button type="submit">Apply SMA windows</button>
      <span v-if="smaError" role="alert">{{ smaError }}</span>
    </form>
    <p>Blue: short SMA ({{ shortWindow }}). Purple: long SMA ({{ longWindow }}). Completed candles only; gaps are unavailable. Changing windows restarts replay.</p>
    <div class="controls">
      <label for="mode">Mode</label><select id="mode" v-model="mode" @change="changeMode"><option value="live">Live / history</option><option value="replay">Replay</option></select>
      <label for="symbol">Symbol / source</label><select id="symbol" v-model="symbol" @change="mode === 'replay' ? chooseSavedSymbol() : load()"><template v-if="mode === 'replay'"><option v-for="recording in saved" :key="recording.symbol" :value="recording.symbol">{{ recording.symbol }} · recorded</option></template><template v-else><option value="AAPL">AAPL · Yahoo</option><option value="SAMPLE">SAMPLE · synthetic CSV</option></template></select>
      <label for="timeframe">Timeframe</label><select id="timeframe" v-model="timeframe" @change="load"><option value="1m">1 minute</option><option value="5m">5 minutes</option><option value="15m">15 minutes</option><option value="1h">Hourly</option><option value="1d">Daily</option></select>
    </div>
    <fieldset class="indicator-editor">
      <legend>Saved indicators for {{ symbol }} · {{ timeframe }}</legend>
      <form class="controls" novalidate @submit.prevent="addIndicator">
        <label for="indicator-type">Indicator type</label><select id="indicator-type" v-model="indicatorType" @change="indicatorWindow = indicatorDefinition.settings.window.default">
          <option v-for="item in indicatorTypes" :key="item.type" :value="item.type">{{ item.label }}</option>
        </select>
        <label for="indicator-name">Indicator name</label><input id="indicator-name" v-model="indicatorName" maxlength="80">
        <label for="indicator-window">Window</label><input id="indicator-window" type="number" :min="indicatorDefinition?.settings.window.minimum" step="1" v-model="indicatorWindow">
        <button :disabled="savingIndicator || !indicatorTypes.length">Add indicator</button>
      </form>
      <p v-if="indicatorDefinition">Uses completed candles: {{ indicatorDefinition.inputs.join(', ') }}. Units: {{ indicatorDefinition.units }}.</p>
      <p v-if="indicatorError" role="alert" class="error">{{ indicatorError }}</p>
      <p>Saved automatically in SQLite for this symbol/source/interval. Adding an indicator restarts replay.</p>
      <table v-if="instances.length" aria-label="Saved indicator values">
        <thead><tr><th>Name</th><th>Type</th><th>Window</th><th>Value at selected candle</th><th>Units</th></tr></thead>
        <tbody><tr v-for="item in instances" :key="item.id"><td>{{ item.name }}</td><td>{{ item.type }}</td><td><input type="number" min="1" step="1" :aria-label="`Window for ${item.name}`" :value="editedWindows[item.id] ?? item.settings.window" @input="editedWindows[item.id] = $event.target.value"><button @click="updateIndicator(item)">Save {{ item.name }} window</button><span>Saved: {{ item.settings.window }}</span></td><td>{{ displaySma(instanceValue(item)) }}</td><td>{{ item.units }}</td></tr></tbody>
      </table>
      <p v-else>No named indicators saved for this chart.</p>
    </fieldset>
    <div v-if="mode === 'replay'" class="replay-controls">
      <label for="replay-start">Receipt range start (UTC, inclusive)</label><input id="replay-start" v-model="replayStart" :disabled="replayRunning" placeholder="2026-11-12T14:30:00Z">
      <label for="replay-end">Receipt range end (UTC, exclusive)</label><input id="replay-end" v-model="replayEnd" :disabled="replayRunning" placeholder="2026-11-12T14:32:00Z">
      <div class="controls"><button :disabled="replayRunning" @click="load">Load selection</button><button :disabled="!replay.total || failed" @click="playReplay">{{ replayRunning ? 'Pause replay' : 'Play replay' }}</button><button :disabled="replayRunning || !replay.total || replay.finished" @click="fetchReplay(replay.step + 1)">Next observation</button><button :disabled="replayRunning || !replay.total" @click="fetchReplay(0)">Restart replay</button></div>
      <p>Replay uses original receipt order at accelerated speed. Source timestamps are unchanged. The recorded session is read-only.</p>
    </div>
    <dl class="feed-status" aria-live="polite">
      <div><dt>Feed status</dt><dd>{{ displayFeedStatus }}</dd></div>
      <div><dt>Browser → FastAPI</dt><dd>{{ transport }}</dd></div>
      <div><dt>Yahoo socket</dt><dd>{{ feed.upstream_connected ? 'connected' : 'disconnected' }}</dd></div>
      <div><dt>Latest source age</dt><dd>{{ age }}</dd></div>
      <div><dt>Session</dt><dd>{{ feed.market_session || 'checking' }}</dd></div>
    </dl>
    <p v-if="feed.latest" class="hint">{{ mode === 'replay' ? 'Replaying source time' : 'Latest source' }}: {{ feed.latest.source_time || 'unknown' }} · Receipt: {{ feed.latest.receipt_time }} · Price: {{ feed.latest.price }} · Observation #{{ feed.latest.observation_id }} / receipt #{{ feed.latest.receipt_id }}</p>
    <button v-if="source === 'yahoo' && mode !== 'replay'" :disabled="controlling" @click="controlFeed">{{ feed.enabled ? 'Disconnect Yahoo feed' : 'Connect Yahoo feed' }}</button>
    <p role="status" :class="{ error: failed }">{{ status }}</p>
    <div ref="container" class="chart" aria-label="Backend candlesticks above aligned trading volume bars"></div>
    <div v-if="rows.length" class="inspection">
      <label for="candle">Inspect candle (UTC)</label>
      <select id="candle" v-model="selectedTime" @change="selectionPinned = true">
        <option v-for="row in rows" :key="row.time" :value="row.time">{{ utcLabel(row.time) }}</option>
      </select>
      <button v-if="selectionPinned" @click="selectionPinned = false">Use hover selection</button>
      <p class="hint">Dropdown selections stay pinned. Hover over a candle or choose its UTC start. Candles follow the exchange regular session.</p>
      <dl v-if="selected" aria-live="polite">
        <div><dt>Date / time</dt><dd>{{ utcLabel(selected.time) }}</dd></div>
        <div v-for="key in ['open', 'high', 'low', 'close']" :key="key"><dt>{{ key }}</dt><dd>{{ selected[key] }}</dd></div>
        <div><dt>Short SMA</dt><dd>{{ displaySma(selectedSma?.short) }}</dd></div>
        <div><dt>Long SMA</dt><dd>{{ displaySma(selectedSma?.long) }}</dd></div>
        <div><dt>Crossover</dt><dd>{{ selectedSma?.signal || 'None' }}</dd></div>
        <div><dt>Volume</dt><dd>{{ selected.volume == null ? 'Unknown' : `${selected.volume} shares` }}</dd></div>
        <div><dt>Candle state</dt><dd>{{ selectedStatus?.ended ? 'Ended' : 'Still forming' }}{{ selectedStatus?.coverage_complete ? '' : ' · partial coverage' }}</dd></div>
      </dl>
    </div>
    <ul aria-label="Confirmed SMA crossovers"><li v-for="row in signals" :key="row.timestamp">{{ row.timestamp }} · SMA {{ row.signal }} · Short {{ displaySma(row.short) }} / Long {{ displaySma(row.long) }}</li></ul>
    <AskChart :freeze-request="freezeRequest" :available="source === 'yahoo' && !!selectedStatus?.complete" />
    <PaperAutomation :view="paperView" :mode="mode" :short="shortWindow" :long="longWindow" />
    <PaperAccount ref="paperComponent" :view="paperView" :mode="mode" />
    <p class="attribution">TradingView Lightweight Charts™<br>Copyright (с) 2025 TradingView, Inc. <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView</a></p>
  </section>
</template>

<style scoped>
section { background: white; border: 1px solid #dce4e9; border-radius: 12px; padding: 24px; }
.chart-heading { display: flex; gap: 16px; justify-content: space-between; align-items: center; flex-wrap: wrap; }
h2 { font-size: 22px; margin: 0; }
.chart-heading p, .hint, .attribution { font-size: 14px; color: #536878; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 18px 0; }
.feed-status dd { font-size: 15px; }
.replay-controls { display: grid; gap: 8px; margin: 16px 0; }
.replay-controls input { padding: 8px; font: inherit; }
.indicator-editor { border: 1px solid #dce4e9; border-radius: 8px; margin: 16px 0; }
th, td { padding: 8px; text-align: left; border-bottom: 1px solid #dce4e9; }
#indicator-name { width: 160px; }
.chart { height: 530px; width: 100%; }
.inspection { margin-top: 20px; border-top: 1px solid #e1e7ec; padding-top: 20px; }
label { font-weight: 600; margin-right: 12px; }
input { width: 100px; padding: 8px; font: inherit; }
.replay-controls input { width: auto; }
select { font: inherit; padding: 8px; max-width: 100%; }
dl { display: flex; flex-wrap: wrap; gap: 16px 32px; }
dt { font-size: 13px; text-transform: capitalize; color: #536878; }
dd { margin: 0; font-weight: 600; }
.error { color: #aa2638; }
</style>
