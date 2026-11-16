import {createChart,CandlestickSeries,HistogramSeries,LineSeries,createSeriesMarkers} from 'lightweight-charts'
import {chartRows,utcLabel} from './chartAdapter.js'
function crc32(bytes) {
  let crc=0xffffffff
  for (const byte of bytes) {crc^=byte;for(let k=0;k<8;k++)crc=(crc>>>1)^((crc&1)?0xedb88320:0)}
  return (crc^0xffffffff)>>>0
}
// Bind the browser export to the immutable snapshot. No page/UI pixels are captured.
export function bindPng(dataUrl, metadata) {
  const raw=Uint8Array.from(atob(dataUrl.split(',')[1]),c=>c.charCodeAt(0))
  const data=new TextEncoder().encode('market_snapshot\0'+JSON.stringify(metadata))
  const type=new TextEncoder().encode('tEXt'),chunk=new Uint8Array(data.length+12),view=new DataView(chunk.buffer)
  view.setUint32(0,data.length);chunk.set(type,4);chunk.set(data,8);view.setUint32(data.length+8,crc32(chunk.slice(4,data.length+8)))
  const output=new Uint8Array(raw.length+chunk.length)
  output.set(raw.slice(0,-12));output.set(chunk,raw.length-12);output.set(raw.slice(-12),raw.length-12+chunk.length)
  let binary='';for(let i=0;i<output.length;i+=8192)binary+=String.fromCharCode(...output.subarray(i,i+8192))
  return 'data:image/png;base64,'+btoa(binary)
}
export async function captureChart(host,snapshot) {
  const chart=createChart(host,{width:1000,height:560,layout:{background:{color:'#ffffff'},textColor:'#26384a',attributionLogo:true},
    timeScale:{timeVisible:true,secondsVisible:false},localization:{timeFormatter:utcLabel}})
  try {
    const data=chartRows(snapshot.chart.candles)
    const candles=chart.addSeries(CandlestickSeries,{upColor:'#087f70',downColor:'#c34252',wickUpColor:'#087f70',wickDownColor:'#c34252',borderVisible:false})
    candles.setData(data.map(({time,open,high,low,close})=>({time,open,high,low,close})))
    const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},title:'Volume (unknown = gap)'},1)
    volume.setData(data.map(r=>r.volume==null?{time:r.time}:{time:r.time,value:r.volume,color:r.color}))
    chart.panes()[1].setHeight(110)
    for(const [key,color] of [['short','#2563eb'],['long','#a855f7']]) {
      const series=chart.addSeries(LineSeries,{color,lineWidth:3,title:`${key} SMA ${snapshot.indicators[key+'_window']}`,priceLineVisible:false})
      series.setData(snapshot.chart.sma.values.map(r=>({time:Date.parse(r.timestamp)/1000,...(r[key]==null?{}:{value:r[key]})})))
    }
    createSeriesMarkers(candles,[{time:Date.parse(snapshot.candle_timestamp)/1000,position:'aboveBar',shape:'circle',color:'#26384a',text:'Selected cutoff'}])
    for(const [index,item] of (snapshot.chart.indicators || []).entries()) {
      const series=chart.addSeries(LineSeries,{color:['#b45309','#0e7490','#be185d'][index%3],title:item.name,priceLineVisible:false},item.pane==='price'?0:2)
      series.setData(item.values.map(r=>({time:Date.parse(r.timestamp)/1000,...(r.value==null?{}:{value:r.value})})))
    }
    chart.timeScale().fitContent()
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
    const png=chart.takeScreenshot().toDataURL('image/png')
    return bindPng(png,{snapshot_id:snapshot.snapshot_id,sha256:snapshot.sha256,chart_range:snapshot.capture_range})
  } finally {chart.remove()}
}
