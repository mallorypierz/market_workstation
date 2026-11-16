<script setup>
import {computed, onMounted, onBeforeUnmount, ref, watch} from 'vue'
const props = defineProps({view:Object, mode:String})
const state=ref(null), quantity=ref(1), message=ref(''), busy=ref(false), accountId=ref('live')
defineExpose({accountId})
const lastRequest=ref(null), replayKey=ref('')
let timer, active=true, serial=Promise.resolve()
const isReplay=computed(()=>props.mode==='replay')
const held=computed(()=>state.value?.positions.find(p=>p.symbol==='AAPL')?.quantity || 0)
const supported=computed(()=>props.view?.symbol==='AAPL')
const pnlMoney=value=>value == null ? 'Unavailable' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value)
const money=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100)
const selectionKey=()=>props.view?.replay ? JSON.stringify([props.view.symbol,props.view.replay.start,props.view.replay.end,props.view.replay.snapshot_cutoff]) : ''
async function api(path,body) {
  const response=await fetch(path,body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {})
  const data=await response.json()
  if (!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : 'Invalid paper account request')
  return data
}
async function refresh() {
  if (!accountId.value) return
  const id=accountId.value
  const data=await api(`/api/paper/account?account_id=${encodeURIComponent(id)}`)
  if(active && id===accountId.value) state.value=data
}
async function syncReplay() {
  if (!isReplay.value || !accountId.value) return
  if(selectionKey()!==replayKey.value) throw new Error('Selection changed. Start a new replay paper account.')
  const id=accountId.value
  const data=await api('/api/paper/replay/advance',{account_id:id,step:props.view.replay.step})
  if(active && id===accountId.value) state.value=data
}
function enqueue(task) { serial=serial.catch(()=>{}).then(task); return serial }
async function startReplay() {
  busy.value=true
  try {
    const view=props.view
    const id=`replay-${crypto.randomUUID()}`
    const data=await api('/api/paper/replay',{account_id:id,symbol:view.symbol,...view.replay})
    accountId.value=id; state.value=data; replayKey.value=selectionKey(); lastRequest.value=null
    message.value='New replay paper account starts here. Only later replay arrivals may fill orders.'
  } catch(error) {message.value=error.message}
  finally {busy.value=false}
}
async function send(action, retry=false) {
  busy.value=true
  try {
    await enqueue(async()=>{
      await syncReplay()
      const body=retry ? lastRequest.value : {request_id:crypto.randomUUID(),account_id:accountId.value,symbol:'AAPL',action,quantity:['buy','sell'].includes(action)?Number(quantity.value):null}
      if(!body) return
      lastRequest.value=body
      localStorage.setItem(`paper-last-${accountId.value}`,JSON.stringify(body))
      const data=await api('/api/paper/actions',body)
      message.value=`${data.status}${data.id ? ` · Order #${data.id}` : ''}${data.rejection_reason ? ` · ${data.rejection_reason}` : ''} · Request ${body.request_id}`
      await refresh()
    })
  } catch(error) {message.value=`${error.message}. Retry the same request if its result is unknown.`}
  finally {busy.value=false}
}
watch(()=>[props.mode,props.view?.replay?.step,selectionKey()],()=>{
  if(isReplay.value) {
    if(accountId.value==='live' || (replayKey.value && replayKey.value!==selectionKey())) {accountId.value='';state.value=null;lastRequest.value=null}
    if(accountId.value) enqueue(syncReplay).catch(error=>message.value=error.message)
  } else if(accountId.value!=='live') {accountId.value='live'; replayKey.value='';refresh().catch(error=>message.value=error.message)}
})
onMounted(()=>{
  try {lastRequest.value=JSON.parse(localStorage.getItem('paper-last-live'))} catch {}
  refresh().catch(error=>message.value=error.message)
  timer=setInterval(()=>{if(!busy.value) refresh().catch(error=>message.value=error.message)},1000)
})
onBeforeUnmount(()=>{active=false;clearInterval(timer)})
</script>
<template>
<section class="paper" aria-label="Local paper account">
  <h2>Paper account · simulated only</h2>
  <p>No real trades. Zero fees. Orders wait for the next eligible observed price after submission; available cash and shares are rechecked at fill.</p>
  <p v-if="state?.data_label"><strong>{{state.data_label}}</strong></p>
  <p v-if="!supported">Paper execution is available for AAPL observations only.</p>
  <button v-if="isReplay" :disabled="busy || !supported || !view?.replay" @click="startReplay">Start new replay paper account</button>
  <p v-if="isReplay">Replay paper accounts are independent. Rewinding requires a new account; existing orders and fills remain recorded.</p>
  <template v-if="state">
    <p>Account: {{accountId}} · {{state.mode}}</p>
    <dl><div><dt>Cash balance</dt><dd>{{money(state.cash_cents)}}</dd></div><div><dt>AAPL shares held</dt><dd>{{held}}</dd></div><div><dt>Persisted fills</dt><dd>{{state.fills.length}}</dd></div></dl>
    <div class="actions"><label for="paper-quantity">Paper shares</label><input id="paper-quantity" type="number" step="1" min="1" v-model="quantity">
      <button :disabled="busy || !supported" @click="send('buy')">Buy shares</button><button :disabled="busy || !supported" @click="send('sell')">Sell shares</button>
      <button :disabled="busy || !supported" @click="send('close')">Close position</button><button :disabled="busy || !supported" @click="send('hold')">Hold</button><button :disabled="busy || !supported" @click="send('wait')">Wait</button>
      <button :disabled="busy || !lastRequest || lastRequest.account_id!==accountId" @click="send(null,true)">Retry last request</button>
    </div>
    <details open class="pnl-history">
      <summary>Profit &amp; loss history</summary>
      <p>Weighted average purchase cost · zero fees. Earlier rows remain available. All amounts are USD.</p>
      <p v-if="state.pnl_current?.valuation_status === 'unavailable'" role="status">Open-position valuation unavailable: no usable valuation price.</p>
      <p>Current realized: {{pnlMoney(state.pnl_current?.realized)}} · Unrealized: {{pnlMoney(state.pnl_current?.unrealized)}} · Total P&amp;L: {{pnlMoney(state.pnl_current?.total)}}</p>
      <p v-if="!state.pnl_history?.length">No P&amp;L events recorded yet.</p>
      <div v-else class="scroll"><table aria-label="Profit and loss history"><thead><tr><th>Event / symbol</th><th>Event UTC</th><th>Cash</th><th>Shares</th><th>Average cost</th><th>Price used</th><th>Realized</th><th>Unrealized</th><th>Total P&amp;L</th><th>Valuation source / UTC</th></tr></thead><tbody>
        <tr v-for="row in state.pnl_history" :key="row.id"><td>#{{row.id}} {{row.event_type}} · {{row.symbol}}<br>{{row.event_key}}</td><td>{{row.event_time}}</td><td>{{money(row.cash_cents)}}</td><td>{{row.quantity}}</td><td>{{row.average_cost == null ? '—' : pnlMoney(row.average_cost)}}</td><td>{{pnlMoney(row.price)}}</td><td>{{pnlMoney(row.realized)}}</td><td>{{pnlMoney(row.unrealized)}}</td><td>{{pnlMoney(row.total)}}</td><td>{{row.price_source}}<br>{{row.price_time || 'Unavailable'}}<br>Observation {{row.observation_id ?? '—'}} · receipt {{row.knowledge_receipt ?? '—'}}<br>{{row.valuation_status}}</td></tr>
      </tbody></table></div>
    </details>
    <h3>Paper order history</h3><div class="scroll"><table><thead><tr><th>Order</th><th>Symbol</th><th>Side / action</th><th>Shares</th><th>Submitted UTC</th><th>Status / reason</th></tr></thead><tbody>
      <tr v-for="order in state.orders" :key="order.id"><td>{{order.id}}</td><td>{{order.symbol}}</td><td>{{order.side}} / {{order.action}}</td><td>{{order.quantity ?? order.requested_quantity_json}}</td><td>{{order.submitted_at}}</td><td>{{order.status}} {{order.rejection_reason}}</td></tr>
    </tbody></table></div>
    <h3>Paper fills</h3><div class="scroll"><table><thead><tr><th>Order</th><th>Shares / price</th><th>Observation / receipt</th><th>Execution UTC</th></tr></thead><tbody>
      <tr v-for="fill in state.fills" :key="fill.id"><td>{{fill.order_id}}</td><td>{{fill.quantity}} @ {{money(fill.price_cents)}}</td><td>{{fill.observation_id}} / {{fill.receipt_id}}</td><td>{{fill.executed_at}}</td></tr>
    </tbody></table></div>
  </template>
  <p role="status">{{message}}</p>
</section>
</template>
<style scoped>
.pnl-history {margin: 20px 0; border:1px solid #dce4e9; padding:12px} summary {font-weight:bold;cursor:pointer} .pnl-history table {font-size:12px} .pnl-history td {overflow-wrap:anywhere;min-width:55px} .paper {border-top:2px solid #dce4e9;margin-top:24px;padding-top:16px} .actions {display:flex;gap:10px;flex-wrap:wrap;align-items:center} input {width:90px;font:inherit;padding:8px} dl {display:flex;gap:40px} dd {margin:0;font-weight:bold} .scroll {overflow:auto} table {width:100%;font-size:14px;text-align:left} th,td {padding:8px;border-bottom:1px solid #dce4e9}
</style>
