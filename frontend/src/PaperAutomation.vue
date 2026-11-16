<script setup>
import {ref,watch,onMounted,onBeforeUnmount,nextTick} from 'vue'
import {captureChart} from './chartCapture.js'
const props=defineProps({view:Object,mode:String,short:Number,long:Number})
const state=ref(null),error=ref(''),busy=ref(false),host=ref(null),enabled=ref(false)
let timer,alive=true,starting=false
async function api(path,body) {
  const r=await fetch(path,body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:!body?.image}:{})
  const text=await r.text();let data;try{data=JSON.parse(text)}catch{throw new Error(`Automation HTTP ${r.status}`)}
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Automation request failed');return data
}
async function refresh() {
  if(!state.value?.control)return
  state.value=await api('/api/automation/'+state.value.control.id)
  enabled.value=!!state.value.control.enabled
}
async function start() {
  starting=true;error.value=''
  try{
    state.value=await api('/api/automation/start',{symbol:props.view.symbol,interval:props.view.timeframe,short:props.short,long:props.long,account_id:'live'})
    enabled.value=!!state.value.control.enabled
    localStorage.setItem('paper-automation-control',state.value.control.id)
  }catch(e){error.value=e.message}finally{starting=false}
  pump()
}
async function stop() {
  enabled.value=false
  if(!state.value?.control)return
  try {state.value=await api('/api/automation/'+state.value.control.id+'/stop',{})}
  catch(e){error.value='Stop could not reach the backend: '+e.message+' Retry Stop before relying on it.'}
}
async function pump() {
  if(!alive||!enabled.value||busy.value||starting||props.mode==='replay')return
  const c=state.value.control,view=props.view
  if(!view||view.symbol!==c.symbol||view.timeframe!==c.interval||props.short!==c.short||props.long!==c.long){await stop();return}
  const known=new Set((state.value.jobs||[]).map(j=>j.candle))
  const candidates=view.candles.filter(r=>view.status[r.timestamp]?.complete && r.timestamp>c.after_candle && !known.has(r.timestamp))
  if(!candidates.length)return
  busy.value=true
  try{
    for(const row of candidates){
      if(!enabled.value)break
      const job=await api(`/api/automation/${c.id}/candles`,{generation:c.generation,candle_timestamp:row.timestamp})
      if(job.status!=='awaiting_image')continue
      let image=null
      try{await nextTick();image=await captureChart(host.value,job.snapshot)}catch(e){error.value='Capture unavailable; analysis will be recorded and execution skipped: '+e.message}
      if(!enabled.value)break
      await api(`/api/automation/jobs/${job.id}/analyze`,{image})
      await refresh()
    }
  }catch(e){error.value=e.message}
  finally{busy.value=false;await refresh().catch(e=>error.value=e.message)}
}
watch(()=>[props.view,props.mode,props.short,props.long],()=>{if(props.mode==='replay'&&enabled.value)stop();else pump()})
onMounted(async()=>{
  const id=localStorage.getItem('paper-automation-control')
  if(id){state.value={control:{id},jobs:[]};try{await refresh()}catch{state.value=null}}
  timer=setInterval(async()=>{try{await refresh();await pump()}catch(e){error.value=e.message}},2000)
})
onBeforeUnmount(()=>{alive=false;clearInterval(timer);if(enabled.value)stop()})
const money=cents=>'$'+(cents/100).toFixed(2)
</script>
<template>
<section class="automation" aria-label="Paper automation">
  <h3>Paper automation · simulation only</h3>
  <p>Newly completed candles receive a fresh frozen PNG, analyst proposal and reviewer verdict. Approved orders wait for the next observed price. Manual chart questions never execute.</p>
  <button :disabled="enabled || !view?.candles?.length || view?.symbol!=='AAPL' || mode==='replay'" @click="start">Start paper automation</button>
  <button :disabled="!state?.control" @click="stop">Stop paper automation</button>
  <p role="status">{{ enabled?'Enabled':'Stopped' }}{{ busy?' · analysis in progress':'' }}. Stop invalidates pending replies and unfilled automated orders.</p>
  <p v-if="error" role="alert">{{ error }}</p>
  <div ref="host" class="capture-host" aria-hidden="true"></div>
  <div v-if="state?.account">
    <p><strong>Account {{ state.account.id }}{{ state.test_account?' · DISPOSABLE TEST ACCOUNT':'' }}</strong> · Cash {{ money(state.account.cash_cents) }} · Shares {{ state.account.positions.find(p=>p.symbol==='AAPL')?.quantity || 0 }} · Fills {{ state.account.fills.length }}</p>
    <p>Realized P&amp;L {{ state.account.pnl_current.realized ?? 'unavailable' }} · Unrealized {{ state.account.pnl_current.unrealized ?? 'unavailable' }}</p>
    <article v-for="job in state.jobs" :key="job.id">
      <h4>{{ job.candle }} · {{ job.symbol }} {{ job.interval }} · {{ job.status }}</h4>
      <p>Python crossover: {{ job.snapshot?.indicators?.at_candle?.signal || 'none / unavailable' }} · Analyst: {{ job.decision?.proposal?.action || 'unavailable' }} · Reviewer: {{ job.decision?.roles?.reviewer?.verdict || 'not completed' }} · Python final: {{ job.decision?.final_check?.passed?'pass':'not approved' }}</p>
      <p v-if="job.decision_id">Decision <a :href="'/api/decisions/'+job.decision_id" target="_blank">{{ job.decision_id }}</a> · {{ job.decision?.model_call }} <a v-if="job.decision?.image" :href="job.decision.image.url" target="_blank">Frozen PNG</a></p>
      <p>Order {{ job.order_id || 'none' }} · Fill {{ job.fill_id || 'none' }} · {{ job.reason || 'No skip reason' }}</p>
      <p v-if="job.execution">Account after execution: {{ money(job.execution.cash_cents) }} · {{ job.execution.shares }} shares · Decision {{ job.execution.decision_id }}</p>
    </article>
  </div>
</section>
</template>
<style scoped>
.automation{margin:20px 0;padding:20px;border:2px solid #607b90;border-radius:10px}button{margin-right:12px;padding:10px}article{border-top:1px solid #ccd5dd;padding-top:8px;margin-top:14px}p{line-height:1.5;overflow-wrap:anywhere}[role=alert]{color:#a52c3c}.capture-host{position:fixed;left:-12000px;top:0;width:1000px;height:560px}
</style>
