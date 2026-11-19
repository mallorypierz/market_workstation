<script setup>
import {ref,onMounted,onBeforeUnmount} from 'vue'
const props=defineProps({mode:String})
const short=ref(2),long=ref(3),timeframe=ref('1m'),runs=ref([]),identity=ref(''),state=ref(null),message=ref(''),busy=ref(false)
let timer,active=true,lastStart=null
const money=cents=>cents==null?'Unavailable':`$${(cents/100).toFixed(2)}`
async function api(path,body){
  const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})
  const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Invalid strategy request');return data
}
async function refresh(){
  if(!identity.value)return
  const id=identity.value,data=await api(`/api/strategy/${encodeURIComponent(id)}`)
  if(active&&id===identity.value)state.value=data
}
async function choose(){localStorage.setItem('sma-run',identity.value);state.value=null;await perform(refresh)}
async function perform(task){busy.value=true;try{await task();message.value=''}catch(e){message.value=e.message}finally{busy.value=false}}
async function start(retry=false){await perform(async()=>{
  if(!retry){
    const a=Number(short.value),b=Number(long.value)
    if(!Number.isSafeInteger(a)||!Number.isSafeInteger(b)||a<=0||a>=b)throw Error('Use positive whole windows with short smaller than long.')
    lastStart={run_id:crypto.randomUUID(),symbol:'AAPL',timeframe:timeframe.value,short:a,long:b}
    localStorage.setItem('sma-start-request',JSON.stringify(lastStart))
  }
  if(!lastStart)throw Error('No start request to retry')
  const data=await api('/api/strategy/start',lastStart)
  runs.value=await api('/api/strategy');identity.value=data.run.id;state.value=data;localStorage.setItem('sma-run',identity.value)
})}
async function stop(){await perform(async()=>{state.value=await api(`/api/strategy/${identity.value}/stop`,{})})}
onMounted(async()=>{
  try{lastStart=JSON.parse(localStorage.getItem('sma-start-request'));identity.value=localStorage.getItem('sma-run')||''}catch{}
  await perform(async()=>{runs.value=await api('/api/strategy');if(!runs.value.some(r=>r.id===identity.value))identity.value='';await refresh()})
  timer=setInterval(()=>{if(!busy.value)perform(refresh)},1000)
})
onBeforeUnmount(()=>{active=false;clearInterval(timer)})
</script>
<template>
<section aria-label="Deterministic SMA strategy" class="strategy">
<h2>SMA strategy · simulated only · no AI</h2>
<p>AAPL: buy one share on a confirmed upward crossover when flat and affordable; close on a downward crossover. No borrowing, shorting or pyramiding. Each new run has its own $1,000 account.</p>
<p>Orders wait for a later eligible receipt. Zero fees, spread and slippage; full fills. Stale source quotes may fill. Evaluation advances on receipts, not a timer; unfinished candles wait for another receipt. Closing this page does not stop an enabled run.</p>
<p v-if="props.mode==='replay'">Chart replay does not drive this strategy. Existing runs continue on forward receipts; switch to Live / history to start a run.</p>
<form @submit.prevent="start(false)">
<label>Strategy short window <input aria-label="Strategy short window" type="number" min="1" step="1" v-model="short" required></label>
<label>Strategy long window <input aria-label="Strategy long window" type="number" min="1" step="1" v-model="long" required></label>
<label>Strategy timeframe <select aria-label="Strategy timeframe" v-model="timeframe"><option v-for="t in ['1m','5m','15m','1h','1d']" :key="t">{{t}}</option></select></label>
<button :disabled="busy||props.mode==='replay'">Start new SMA run</button>
<button type="button" :disabled="busy||props.mode==='replay'" @click="start(true)">Retry SMA start</button>
</form>
<label>Saved SMA run <select aria-label="Saved SMA run" v-model="identity" @change="choose"><option value="">Select a run</option><option v-for="r in runs" :value="r.id" :key="r.id">{{r.id}} · {{r.timeframe}} · {{r.short}}/{{r.long}}</option></select></label>
<p role="alert" v-if="message">{{message}}</p>
<template v-if="state">
<p><strong>{{state.run.enabled?'Running':'Stopped'}}</strong> · Run {{state.run.id}} · Account {{state.run.account_id}} · AAPL {{state.run.timeframe}} · SMA {{state.run.short}}/{{state.run.long}}</p>
<p v-if="state.data_label"><strong>{{state.data_label}}</strong></p>
<button :disabled="busy||!state.run.enabled" @click="stop">Stop SMA run</button>
<p>Stop cancels unfilled orders. A stopped run stays stopped, including on retry/restart; start a new run for a new account.</p>
<p>Cash {{money(state.account.cash_cents)}} · Shares {{state.account.positions.find(p=>p.symbol==='AAPL')?.quantity||0}} · Fills {{state.account.fills.length}}</p>
<p>Realized {{state.account.pnl_current?.realized??0}} · Unrealized {{state.account.pnl_current?.unrealized??(state.account.positions.some(p=>p.quantity)?'Unavailable':0)}} · Valuation {{state.account.pnl_current?.price_time||'No valuation yet'}}</p>
<p>Processed receipt {{state.run.cursor}} · Last completed candle {{state.run.last_candle||'None'}}. Decisions are frozen; later chart revisions do not rewrite earlier fills.</p>
<p v-if="!state.events.length">Waiting for newly completed candles. Existing history is warm-up only.</p>
<div class="scroll"><table aria-label="SMA strategy decisions"><thead><tr><th>Candle / receipt / decision time</th><th>Short / long / signal</th><th>Action / reason</th><th>Account before</th><th>Order / status</th><th>Fill / price / receipt</th></tr></thead><tbody>
<tr v-for="e in state.events" :key="e.id"><td>{{e.candle}}<br>#{{e.receipt_id}} · {{e.decision_time}}</td><td>{{e.short_value??'Unavailable'}} / {{e.long_value??'Unavailable'}} / {{e.signal||'none'}}</td><td>{{e.action}} · {{e.reason}}</td><td>{{money(e.cash_before)}} / {{e.shares_before}} shares</td><td>{{e.order_id??'—'}} · {{e.order_status||'skipped'}}<br>{{e.rejection_reason}}</td><td>{{e.fill_id??'—'}} · {{money(e.fill_price_cents)}}<br>receipt {{e.fill_receipt??'—'}} · {{e.fill_time}}</td></tr>
</tbody></table></div>
<details><summary>Strategy P&amp;L history</summary><div v-for="p in state.account.pnl_history" :key="p.id">Fill {{p.fill_id??'—'}} · {{p.event_time}} · {{p.price_source}} · Cash {{money(p.cash_cents)}} · Shares {{p.quantity}} · Realized {{p.realized}} · Unrealized {{p.unrealized??'Unavailable'}}</div></details>
</template>
</section>
</template>
<style scoped>
.strategy{border-top:2px solid #dce4e9;margin-top:24px;padding-top:16px}form{display:flex;gap:12px;flex-wrap:wrap;align-items:center}input{width:80px}input,select{padding:8px}table{width:100%;text-align:left;font-size:13px}td,th{padding:8px;border-bottom:1px solid #dce4e9}.scroll{overflow:auto}td{min-width:110px}
</style>
