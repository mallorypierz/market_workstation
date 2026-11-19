<script setup>
import {ref,computed,onMounted} from 'vue'
import BacktestCharts from './BacktestCharts.vue'
const datasets=ref([]),runs=ref([]),dataset=ref('recorded'),selected=ref(localStorage.getItem('backtest-id')||''),saved=ref(null),error=ref(''),busy=ref(false),status=ref('Idle')
const form=ref({symbol:'AAPL',timeframe:'1m',warmup_start:'',start:'',end:'',short:'2',long:'3',cash:'1000.00'})
const choice=computed(()=>datasets.value.find(d=>d.id===dataset.value)),result=computed(()=>saved.value?.result)
const money=v=>v==null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(v)
const percent=v=>v==null?'Unavailable':(100*v).toFixed(4)+'%'
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);let j;try{j=await r.json()}catch{throw Error(`Backend unavailable (HTTP ${r.status}). Retry loading saved results.`)}if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail));return j}
function defaults(){const d=choice.value;if(d)Object.assign(form.value,{symbol:d.symbol,timeframe:d.default_timeframe||d.timeframes[0],warmup_start:d.warmup_start||'',start:d.start||'',end:d.end||''})}
async function catalog(){datasets.value=await api('/api/backtest-datasets');runs.value=await api('/api/backtests')}
async function load(){if(!selected.value)return;busy.value=true;error.value='';try{saved.value=await api('/api/backtests/'+encodeURIComponent(selected.value));localStorage.setItem('backtest-id',selected.value);status.value=saved.value.status}catch(e){error.value=`Backend / saved result unavailable: ${e.message}`}finally{busy.value=false}}
async function refresh(){error.value='';try{await catalog();if(selected.value)await load()}catch(e){error.value=`Backend unavailable: ${e.message}`}}
async function run(){
 error.value='';const f=form.value
 if(!choice.value?.available){error.value='Selected dataset is unavailable; choose an available dataset.';return}
 if(!/^\d+$/.test(String(f.short))||!/^\d+$/.test(String(f.long))||+f.short<=0||+f.short>=+f.long){error.value='SMA windows must be positive whole numbers with short < long.';return}
 if(!/^\d+(\.\d{1,2})?$/.test(f.cash)){error.value='Starting cash requires positive dollars with at most two decimal places.';return}
 const [d,c='']=f.cash.split('.'),cents=Number(d)*100+Number(c.padEnd(2,'0'))
 if(!Number.isSafeInteger(cents)||cents<=0||cents>1e12){error.value='Starting cash must be positive and at most $10 billion.';return}
 if(!['warmup_start','start','end'].every(k=>/Z$/.test(f[k])&&Number.isFinite(Date.parse(f[k])))||!(Date.parse(f.warmup_start)<=Date.parse(f.start)&&Date.parse(f.start)<Date.parse(f.end))){error.value='Use UTC timestamps ending Z, with warm-up ≤ start < end.';return}
 busy.value=true;status.value='Running simulation';saved.value=null
 const id=crypto.randomUUID();selected.value=id;localStorage.setItem('backtest-id',id)
 try{saved.value=await api('/api/backtests',{run_id:id,dataset:dataset.value,symbol:f.symbol,timeframe:f.timeframe,warmup_start:f.warmup_start,start:f.start,end:f.end,short:Number(f.short),long:Number(f.long),initial_cash_cents:cents});status.value=saved.value.status;await catalog()}
 catch(e){status.value='Failed or connection interrupted';error.value=e.message+' Reload saved results before retrying an interrupted run.'}finally{busy.value=false}
}
onMounted(async()=>{try{await catalog();defaults();if(selected.value)await load()}catch(e){error.value=`Backend unavailable: ${e.message}`}})
</script>
<template>
<section aria-label="Historical backtest" class="backtest">
<h2>Historical backtest</h2><p><strong>SIMULATION · isolated account · no model or broker</strong></p>
<p>One share on confirmed upward crossing when flat and affordable; close on downward crossing. Signals queue orders for a later eligible price. Live account state is separate.</p>
<form @submit.prevent="run" novalidate>
<div class="fields">
<label>Dataset<select aria-label="Dataset" v-model="dataset" @change="defaults"><option v-for="d in datasets" :value="d.id">{{d.label}} ({{d.count}} records{{d.available?'':', unavailable'}})</option></select></label>
<label>Symbol<select v-model="form.symbol"><option>AAPL</option></select></label>
<label>Timeframe<select v-model="form.timeframe"><option v-for="t in choice?.timeframes" :value="t">{{t}}</option></select></label>
<label>Warm-up start UTC<input v-model="form.warmup_start"/></label><label>Evaluation start UTC<input v-model="form.start"/></label><label>End exclusive UTC<input v-model="form.end"/></label>
<label>Short window<input v-model="form.short" inputmode="numeric"/></label><label>Long window<input v-model="form.long" inputmode="numeric"/></label><label>Starting cash USD<input v-model="form.cash" inputmode="decimal"/></label>
</div><p>Available selection: {{choice?.warmup_start||'Unavailable'}} → {{choice?.end||'Unavailable'}}. {{choice?.provenance}} {{choice?.retrieved_at}}</p>
<button :disabled="busy" type="submit">Run new backtest</button>
</form>
<p role="status">Run status: {{status}} · ID: {{selected||'none'}}</p><p v-if="error" role="alert" class="error">{{error}}</p>
<label>Saved run<select aria-label="Saved run" v-model="selected"><option value="">Select a saved run</option><option v-for="r in runs" :value="r.run_id">{{r.run_id}} · {{r.status}}</option></select></label>
<button :disabled="busy||!selected" @click="load">Load saved result</button> <button :disabled="busy" @click="refresh">Refresh saved results</button>
<template v-if="saved">
<p v-if="saved.error" class="error">{{saved.error}}</p>
<details><summary>Frozen parameters, provenance and execution assumptions</summary><pre>{{saved.metadata}}</pre></details>
<template v-if="result">
<p class="metrics">Cash {{money(result.account.cash)}} · Position {{result.open_positions.map(p=>`${p.quantity} ${p.symbol}`).join(', ')||'0 shares'}} · Equity {{money(result.ending_equity)}}<br/>Return {{percent(result.total_return)}} · Maximum drawdown {{percent(result.max_drawdown)}}<br/>Realized {{money(result.account.pnl_current?.realized)}} · Unrealized {{money(result.account.pnl_current?.unrealized)}}</p>
<p>Sample: {{result.sample.evaluation_completed_candles}} evaluated candles; {{result.sample.warmup_completed_candles}} warm-up; {{result.sample.fills}} fills; {{result.pending_orders.length}} pending orders. {{result.warnings.join('; ')}}</p>
<p>{{result.chart.label}}. Ties retain the last side; the first comparable pair establishes a side without a signal. Only completed candles confirm signals.</p>
<BacktestCharts :result="result"/>
<h3>Frozen decisions → orders → fills</h3><p>Skipped and pending actions remain visible. Expand a row for exact IDs, receipt boundaries and prices.</p>
<div class="scroll"><table aria-label="Backtest decisions"><thead><tr><th>Candle UTC</th><th>Short / long</th><th>Signal</th><th>Action / reason</th><th>Order → fill</th></tr></thead><tbody><tr v-for="(d,i) in result.decisions" :key="i"><td>{{d.timestamp}}</td><td>{{d.short??'Unavailable'}} / {{d.long??'Unavailable'}}</td><td>{{d.signal||'—'}}</td><td>{{d.action}} · {{d.reason}}</td><td><details><summary>{{d.order?`#${d.order.id} ${d.order.status}`:'Skipped'}} → {{d.fill?`#${d.fill.id} ${d.fill.side} ${d.fill.quantity} @ ${money(d.fill.price_cents/100)}`:'No fill'}}</summary><pre>{{d}}</pre></details></td></tr></tbody></table></div>
<details><summary>Full valuation and account trace</summary><pre>{{result.equity_curve}}</pre><pre>{{result.account}}</pre></details>
<a :href="'/api/backtests/'+saved.run_id" target="_blank">Open saved JSON artifact</a>
</template></template>
</section>
</template>
<style scoped>
.backtest{margin-top:32px;padding:22px;background:#fff;border:2px solid #b9cbd8;border-radius:10px}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}label{display:flex;flex-direction:column;font-size:15px}input,select{font:inherit;padding:8px;max-width:100%;box-sizing:border-box}button{margin:8px 0}.error{color:#9e2020;background:#fff0ef;padding:12px}.metrics{background:#edf6f5;padding:16px}.scroll{overflow:auto}table{border-collapse:collapse;font-size:14px;width:100%}td,th{padding:8px;border-bottom:1px solid #ccd5dc;text-align:left;vertical-align:top}pre{font-size:13px;max-height:400px;overflow:auto}summary{cursor:pointer}
</style>
