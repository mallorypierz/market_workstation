<script setup>
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
import {VoiceConnection} from './voiceConnection.js'
const choices=ref([]),selected=ref(''),summary=ref(null),state=ref('Idle'),error=ref(''),microphone=ref(false),sessionId=ref(''),captions=ref([]),audio=ref(null)
let connection
const busy=computed(()=>['Requesting microphone','Connecting','Connected','Ending · microphone released'].includes(state.value))
async function load() {
  error.value=''
  try{const r=await fetch('/api/voice/decisions');if(!r.ok)throw new Error('Cannot load saved decisions');choices.value=await r.json();if(!selected.value)selected.value=choices.value[0]?.id || '';await inspect()}
  catch(e){error.value=e.message}
}
async function inspect() {
  summary.value=null
  if(!selected.value)return
  const id=selected.value
  try{const r=await fetch('/api/voice/decisions/'+encodeURIComponent(id));const b=await r.json();if(!r.ok)throw new Error(b.detail);if(selected.value===id)summary.value=b}
  catch(e){error.value=e.message}
}
function start() {
  captions.value=[];sessionId.value=''
  connection=new VoiceConnection({audio:audio.value,update:p=>{
    if(p.state!==undefined)state.value=p.state;if(p.error!==undefined)error.value=p.error
    if(p.microphone!==undefined)microphone.value=p.microphone;if(p.summary)summary.value=p.summary;if(p.sessionId)sessionId.value=p.sessionId
  },caption:c=>captions.value.push(c)})
  connection.start(selected.value)
}
function end(){connection?.end()}
function leave(){connection?.end(true)}
onMounted(()=>{load();window.addEventListener('pagehide',leave);window.addEventListener('offline',leave)})
onBeforeUnmount(()=>{leave();window.removeEventListener('pagehide',leave);window.removeEventListener('offline',leave)})
</script>
<template>
<section aria-label="Decision voice conversation" class="voice">
<h2>Discuss a recorded decision by voice</h2>
<p>AI-generated voice · read-only conversation. Your microphone audio and this decision summary go to OpenAI when you start. Voice cannot place paper orders.</p>
<label for="voice-decision">Selected decision</label>
<select id="voice-decision" v-model="selected" :disabled="busy" @change="inspect"><option v-for="d in choices" :key="d.id" :value="d.id">{{ d.created_at }} · {{ d.status }} · {{ d.id }}</option></select>
<button :disabled="busy" @click="load">Refresh saved decisions</button>
<p v-if="!choices.length">No saved decisions. Analyze a chart first, then refresh.</p>
<div v-if="summary">
<p>{{ summary.facts_at_decision.symbol }} · {{ summary.facts_at_decision.interval }} · {{ summary.facts_at_decision.decision_time }}<br>{{ summary.facts_at_decision.market_data }} · Model call: {{ summary.model_call }}</p>
<p>Analyst: {{ summary.analyst_proposal?.action || 'not recorded' }} · Reviewer: {{ summary.roles?.reviewer?.verdict || 'not recorded' }} · {{ summary.outcome_note }}</p>
<details><summary>Read-only evidence supplied to voice</summary><pre>{{ JSON.stringify(summary,null,2) }}</pre></details>
</div>
<button :disabled="busy || !summary" @click="start">Start voice</button>
<button :disabled="!busy" @click="end">End voice</button>
<p role="status">{{ state }} · Microphone {{ microphone?'ACTIVE':'off' }}<span v-if="sessionId"> · Session {{ sessionId }}</span></p>
<p v-if="error" role="alert">{{ error }}</p>
<audio ref="audio" autoplay controls aria-label="Voice playback"></audio>
<p>Ask “What did the agents decide for this symbol?” Then ask “What happened to the paper account?” Stay in the same session for follow-ups. The summary is frozen at startup.</p>
<details v-if="captions.length" open><summary>Session captions (not proof of audible playback)</summary><p v-for="(c,i) in captions" :key="i"><strong>{{ c.speaker }}:</strong> {{ c.text }}</p></details>
</section>
</template>
<style scoped>
.voice{padding:20px;margin:24px 0;border:1px solid #9aafc0;border-radius:10px;background:white}select{display:block;max-width:100%;padding:8px}button{margin:8px 8px 8px 0}pre{max-height:300px;overflow:auto;font-size:14px}p{overflow-wrap:anywhere}[role=alert]{color:#a22b38}
</style>
