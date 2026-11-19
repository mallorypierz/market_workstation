<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { createChart, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts'
const props=defineProps({result:Object})
const candles=ref(null),equity=ref(null)
let charts=[]
const time=s=>Math.floor(Date.parse(s)/1000)
function draw(){
 charts.forEach(c=>c.remove());charts=[]
 if(!props.result)return
 const r=props.result,c=createChart(candles.value,{autoSize:true,height:330,timeScale:{timeVisible:true}});charts.push(c)
 const bars=c.addSeries(CandlestickSeries);bars.setData(r.chart.candles.map(b=>({...b,time:time(b.timestamp)})))
 for(const [key,color] of [['short','#1565c0'],['long','#b14c00']]){
  c.addSeries(LineSeries,{color,lineWidth:2,title:`${key} SMA`}).setData(r.chart.sma.values.map(v=>v[key]==null?{time:time(v.timestamp)}:{time:time(v.timestamp),value:v[key]}))
 }
 createSeriesMarkers(bars,r.chart.sma.values.filter(v=>v.signal).map(v=>({time:time(v.timestamp),position:v.signal==='up'?'belowBar':'aboveBar',shape:v.signal==='up'?'arrowUp':'arrowDown',color:v.signal==='up'?'#087f51':'#b32431',text:v.signal==='up'?'UP':'DOWN'})))
 c.timeScale().fitContent()
 const e=createChart(equity.value,{autoSize:true,height:230,timeScale:{timeVisible:true}});charts.push(e)
 const points=new Map(r.equity_curve.map(v=>[time(v.time),v.equity]))
 e.addSeries(LineSeries,{color:'#663399',title:'Equity USD'}).setData([...points].sort((a,b)=>a[0]-b[0]).map(([time,value])=>value==null?{time}:{time,value}));e.timeScale().fitContent()
}
onMounted(draw);watch(()=>props.result,async()=>{await nextTick();draw()});onBeforeUnmount(()=>charts.forEach(c=>c.remove()))
</script>
<template><p>Blue: short SMA · Orange: long SMA · Arrows: confirmed UP / DOWN crossings. Gaps indicate warm-up.</p><div ref="candles" aria-label="Backtest candles and two SMA lines"/><h3>Equity (USD)</h3><div ref="equity" aria-label="Backtest equity curve"/><p>Includes initial cash. Same-second chart points show the last valuation; the full trace retains every step.</p></template>
