import {chromium,expect} from '@playwright/test'
import fs from 'node:fs'
import {pathToFileURL} from 'node:url'
const out=process.env.DEMO_OUT
fs.writeFileSync(out+'/player.html','<body style="margin:0"><video muted style="width:1440px;height:1000px" src="part-4.2-demo.webm"></video></body>')
const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}})
try{
 await page.goto(pathToFileURL(out+'/player.html').href)
 await page.waitForFunction(()=>document.querySelector('video').readyState>=2)
 const duration=await page.locator('video').evaluate(v=>v.duration);expect(duration).toBeGreaterThanOrEqual(30);expect(duration).toBeLessThanOrEqual(60)
 for(const second of [8,19,27,36,38,42,46,53]){
  await page.locator('video').evaluate((v,t)=>new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=t}),second)
  await page.screenshot({path:out+`/frame-${second}.png`})
 }
 fs.writeFileSync(out+'/duration.json',JSON.stringify({duration_seconds:duration,within_30_60:true,method:'Chromium HTMLVideoElement duration, loaded metadata and decoded seeks',checked_seconds:[8,19,27,36,38,42,46,53]},null,2))
}finally{await browser.close()}
