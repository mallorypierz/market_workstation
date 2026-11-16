<script setup>
import { ref } from 'vue'
import CandleChart from './CandleChart.vue'
import DecisionVoice from './DecisionVoice.vue'
const result = ref('Not checked')
const loading = ref(false)
async function checkBackend() {
  loading.value = true
  result.value = 'Checking…'
  try {
    const response = await fetch('/api/health')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    result.value = JSON.stringify(await response.json())
  } catch (error) {
    result.value = `Backend unavailable: ${error.message}`
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main>
    <h1>Market Workstation</h1>
    <CandleChart />
    <DecisionVoice />
    <p>Local connection check</p>
    <button :disabled="loading" @click="checkBackend">Check backend</button>
    <pre aria-live="polite">{{ result }}</pre>
    <p><a href="/api/history">Open synthetic one-minute candle history</a></p>
    <p>Live and synthetic sources are explicitly labeled in the chart. Regular-session candles only.</p>
  </main>
</template>

<style>
body { margin: 0; font: 18px/1.6 system-ui, sans-serif; color: #193046; background: #f3f6f8; }
main { max-width: 1100px; margin: 24px auto; padding: 24px; }
button { padding: 12px 20px; font: inherit; cursor: pointer; }
pre { padding: 16px; background: white; white-space: pre-wrap; }
a { color: #165a8b; }
</style>
