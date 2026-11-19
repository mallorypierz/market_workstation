// Record actual Vue/FastAPI views; captions are narration, never substituted results.
import {chromium,expect} from '@playwright/test'
import fs from 'node:fs'
const out=process.env.DEMO_OUT,browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:out,size:{width:1440,height:1000}}})
await context.addInitScript(()=>localStorage.setItem('backtest-id','demo-constructed'))
const page=await context.newPage(),video=page.video(),start=Date.now()
const until=async seconds=>{const wait=start+seconds*1000-Date.now();if(wait>0)await page.waitForTimeout(wait)}
async function caption(text){await page.evaluate(text=>{let el=document.getElementById('recording-caption');if(!el){el=document.createElement('div');el.id='recording-caption';el.style.cssText='position:fixed;bottom:0;left:0;right:0;z-index:99999;background:#122b40;color:white;padding:18px 24px;font:22px system-ui;box-shadow:0 -2px 8px #aaa';document.body.append(el)}el.textContent=text},text)}
try{
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 await page.goto(process.env.DEMO_URL)
 const bt=page.getByRole('region',{name:'Historical backtest'})
 await expect(bt).toContainText('Cash $1,010.00')
 await caption('0–15s • CONSTRUCTED correctness fixture: SMA 2 / 3. Blue short, orange long; confirmed UP and DOWN markers. Simulation only.')
 await bt.getByLabel('Backtest candles and two SMA lines').scrollIntoViewIfNeeded()
 await until(15)
 await caption('15–30s • UP 16/13 queues buy; later receipt fills 1 @ $100. DOWN 4/9 queues close; later fill $110. No same-receipt fill.')
 const rows=bt.getByRole('table',{name:'Backtest decisions'}).locator('tbody tr')
 await rows.nth(4).locator('summary').click();await rows.nth(4).scrollIntoViewIfNeeded()
 await until(23);await rows.nth(4).locator('summary').click();await bt.locator('.metrics').scrollIntoViewIfNeeded()
 await until(30)
 await bt.getByLabel('Dataset',{exact:true}).selectOption('aapl-2025-daily')
 await bt.getByLabel('Saved run',{exact:true}).selectOption('demo-yahoo-daily');await bt.getByRole('button',{name:'Load saved result',exact:true}).click()
 await expect(bt).toContainText('Cash $999.64')
 await caption('30–50s • REAL saved Yahoo daily bars, Jan–Feb 2025: 33 evaluation bars, 10 fills; equity $999.64, return −0.036%, max drawdown 1.2997%.')
 await bt.locator('.metrics').scrollIntoViewIfNeeded();await until(36)
 await bt.getByLabel('Backtest equity curve').scrollIntoViewIfNeeded();await until(41)
 await bt.getByRole('table',{name:'Backtest decisions'}).locator('tbody tr').nth(2).evaluate(el=>el.scrollIntoView({block:'center'}));await until(45)
 await bt.getByText('Frozen parameters, provenance and execution assumptions',{exact:true}).click();await bt.getByText('Frozen parameters, provenance and execution assumptions',{exact:true}).scrollIntoViewIfNeeded()
 await caption('Assumptions: daily bars become known at close; orders fill at the next supplied open. Zero fees/slippage; dividends excluded. No forced liquidation.')
 await until(50)
 await bt.getByText('Frozen parameters, provenance and execution assumptions',{exact:true}).click();await bt.locator('.metrics').scrollIntoViewIfNeeded()
 await caption('50–56s • Checks: unchanged earlier decisions after future receipts; unfinished candles cannot signal. One stock and a short sample cannot establish future performance.')
 await until(56)
}finally{await context.close();await video.saveAs(out+'/part-4.2-demo.webm');await browser.close()}
fs.writeFileSync(out+'/recording.json',JSON.stringify({status:'recorded',actual_app:true,audio:false,captions:'recording narration overlay; app values unchanged',elapsed_ms:Date.now()-start},null,2))
