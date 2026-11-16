<script setup>
import {ref,nextTick} from 'vue'
import {captureChart} from './chartCapture.js'
const props=defineProps({freezeRequest:Function,available:Boolean})
const snapshot=ref(null),image=ref(''),questions=ref([]),result=ref(null),error=ref(''),busy=ref(false),host=ref(null)
async function api(path,body) {
  const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})
  const text=await r.text();let data
  try {data=JSON.parse(text)} catch {throw new Error(`Backend returned HTTP ${r.status}; check the service and retry the frozen capture.`)}
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request failed');return data
}
async function freeze() {
  error.value='';busy.value=true;result.value=null;image.value='';snapshot.value=null
  try {
    const request=props.freezeRequest() // synchronous selection/range freeze before any await
    questions.value=await api('/api/chart-questions')
    const saved=await api('/api/decision-snapshots',request)
    if(!saved.complete)throw new Error('Cannot capture this cutoff: '+saved.reasons.join('; '))
    snapshot.value=saved;await nextTick()
    image.value=await captureChart(host.value,saved)
  }catch(e){error.value=e.message}finally{busy.value=false}
}
async function analyze() {
  busy.value=true;error.value=''
  try {
    result.value=await api('/api/decisions',{analysis:'chart',snapshot_id:snapshot.value.snapshot_id,
      snapshot_sha256:snapshot.value.sha256,chart_range:snapshot.value.capture_range,image:image.value})
  }catch(e){error.value=e.message}finally{busy.value=false}
}
</script>
<template>
  <section aria-label="Ask about chart" class="analysis">
    <h3>Ask about chart</h3>
    <p>Choose a completed candle, then freeze the visible range through that cutoff. Review the PNG before sending it. Analysis never places an order.</p>
    <button :disabled="busy || !available" @click="freeze">Ask about chart</button>
    <p v-if="busy" role="status">Preparing capture or waiting for analysis…</p>
    <p v-if="error" role="alert">{{ error }} Recapture after correcting the selection.</p>
    <div ref="host" class="capture-host" aria-hidden="true"></div>
    <div v-if="image && snapshot" class="frozen">
      <h4>Frozen chart preview</h4>
      <p><strong>{{ snapshot.symbol }} · {{ snapshot.interval }} · cutoff {{ snapshot.decision_time }}</strong></p>
      <p>Range {{ snapshot.capture_range.from }} → {{ snapshot.capture_range.to }} · UTC<br>{{ snapshot.market_data }}</p>
      <p>Blue: SMA {{ snapshot.indicators.short_window }} · Purple: SMA {{ snapshot.indicators.long_window }}. Unknown volume is a gap. Selected cutoff marks the last candle.</p>
      <img :src="image" alt="Frozen chart sent for analysis" />
      <details open><summary>What the model is asked</summary><ol><li v-for="q in questions" :key="q.name"><strong>{{ q.name }}</strong>: {{ q.instructions }}<br>Allowed: {{ q.choices.map(c=>c.value).join(', ') }}</li></ol></details>
      <p>Frozen account: ${{ snapshot.account.cash.toFixed(2) }} cash · {{ snapshot.account.shares }} shares. Python crossover: {{ snapshot.indicators.at_candle.signal || 'none' }}. Snapshot {{ snapshot.snapshot_id }}.</p>
      <button :disabled="busy || !!result" @click="analyze">Analyze frozen chart</button>
      <p>Live updates and selection changes do not alter this preview. Click Ask about chart again to recapture.</p>
    </div>
    <div v-if="result" aria-label="Chart analysis result" role="status">
      <h4>Model answers · {{ result.model_call }}</h4>
      <p>{{ result.market_data }} · Status: {{ result.status }}</p>
      <table aria-label="Chart analysis answers"><thead><tr><th>Question</th><th>Model answer</th></tr></thead><tbody>
        <tr v-for="q in questions" :key="q.name"><td>{{ q.name }}</td><td>{{ result.answers?.[q.name] || 'Missing' }}</td></tr>
      </tbody></table>
      <p>Python crossover: {{ result.python_crossover || 'unavailable' }} · Visual agreement: {{ result.validation?.visual_matches_python === true ? 'matches' : 'not confirmed' }}</p>
      <p>{{ result.explanation || result.validation?.reason }}</p>
      <p v-if="result.validation?.recapture_required">Recapture the chart with a readable cutoff and enough SMA history before asking again.</p>
      <p>Automated execution eligible: {{ result.order_eligible ? 'yes (proposal only)' : 'no' }} · Order created: no.</p>
      <p>Decision {{ result.decision_id }} <a v-if="result.image" :href="result.image.url" target="_blank">Open saved PNG</a></p>
    </div>
  </section>
</template>
<style scoped>
.analysis{margin:24px 0;padding:20px;border:1px solid #cbd8e4;border-radius:10px;background:#f7fafc}
.capture-host{position:fixed;left:-12000px;top:0;width:1000px;height:560px}
img{display:block;width:100%;max-width:1000px;border:1px solid #dce4e9}
p,li{line-height:1.5;overflow-wrap:anywhere}li{margin-bottom:12px}button{padding:10px 16px}th,td{padding:8px 24px;text-align:left}
[role=alert]{color:#aa2638}a{margin-left:12px}
</style>
