import {chromium,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import fs from 'node:fs'
const browser=await chromium.launch({headless:true}),page=await browser.newPage({baseURL:process.env.SMA_BASE_URL,viewport:{width:1440,height:1000}})
const panel=page.getByRole('region',{name:'Deterministic SMA strategy'}),artifacts=process.env.SMA_ARTIFACTS
const result={status:'failed',provider:'none'},errors=[]
page.on('pageerror',e=>errors.push(e.message))
async function state(){const id=await panel.getByLabel('Saved SMA run').inputValue();const r=await page.request.get(`/api/strategy/${id}`);expect(r.ok()).toBe(true);return r.json()}
async function start(){const previous=await panel.getByLabel('Saved SMA run').inputValue();await panel.getByRole('button',{name:'Start new SMA run',exact:true}).click();await expect.poll(()=>panel.getByLabel('Saved SMA run').inputValue()).not.toBe(previous);await expect(panel).toContainText('Cash $1000.00 · Shares 0 · Fills 0')}
async function quote(minute,price,forming=false){
  execFileSync(process.env.STRATEGY_PYTHON,['-m','backend.strategy_fixture','--database',process.env.MARKET_DB_PATH,'--minute',String(minute),'--price',String(price),...(forming?['--forming']:[])],{cwd:process.env.STRATEGY_ROOT})
  await expect.poll(async()=>(await state()).run.cursor).toBeGreaterThan(0)
}
try{
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 await page.goto(process.env.SMA_BASE_URL)
 await start()
 await expect(panel).toContainText('Running')
 const first=(await state()).run.id
 for(const [i,p] of [[1,10],[2,7],[3,13],[4,19]])await quote(i,p)
 await expect(panel).toContainText('pending')
 let s=await state();expect(s.account.fills).toHaveLength(0);expect(s.account.orders).toHaveLength(1)
 await panel.screenshot({path:artifacts+'/pending.png'})
 await panel.getByRole('button',{name:'Retry SMA start',exact:true}).click()
 expect((await state()).run.id).toBe(first);expect((await state()).account.orders).toHaveLength(1)
 await quote(5,100,true)
 await expect(panel).toContainText('Cash $900.00 · Shares 1 · Fills 1')
 await quote(5,7);await quote(6,1)
 await expect.poll(async()=>(await state()).account.orders.length).toBe(2)
 await quote(7,110,true)
 await expect(panel).toContainText('Cash $1010.00 · Shares 0 · Fills 2')
 s=await state();expect(s.account.pnl_current.realized).toBe(10)
 expect(s.events.filter(e=>e.fill_id).every(e=>e.fill_receipt>e.receipt_id)).toBe(true)
 await panel.screenshot({path:artifacts+'/filled.png'});result.completed=s
 await page.reload();await expect(panel).toContainText('Cash $1010.00 · Shares 0 · Fills 2')
 await panel.getByRole('button',{name:'Stop SMA run',exact:true}).click()
 await expect(panel.getByText('Stopped',{exact:true})).toBeVisible()
 // Second independent run: signal affordable, later fill is too expensive.
 await start()
 await quote(7,13);await quote(8,19)
 await expect.poll(async()=>(await state()).account.orders.some(o=>o.status==='pending')).toBe(true)
 await quote(9,2000,true)
 await expect(panel).toContainText('Insufficient cash at fill')
 await expect(panel).toContainText('Cash $1000.00 · Shares 0 · Fills 0')
 await panel.screenshot({path:artifacts+'/rejected.png'});result.rejected=await state()
 // Third run: stop pending order then deliver more data; no fill or new event.
 await panel.getByRole('button',{name:'Stop SMA run',exact:true}).click()
 await start()
 for(const [i,p] of [[9,7],[10,1],[11,13],[12,19]])await quote(i,p)
 await expect.poll(async()=>(await state()).account.orders.some(o=>o.status==='pending')).toBe(true)
 await panel.getByRole('button',{name:'Stop SMA run',exact:true}).click()
 await expect(panel).toContainText('Strategy stopped before fill')
 const stopped=await state();await quote(13,100,true)
 await page.waitForTimeout(1500)
 expect((await state()).events).toEqual(stopped.events);expect((await state()).account.fills).toHaveLength(0)
 await panel.getByRole('button',{name:'Retry SMA start',exact:true}).click()
 await expect(panel.getByText('Stopped',{exact:true})).toBeVisible()
 result.stopped=await state();await panel.screenshot({path:artifacts+'/stopped.png'})
 expect(errors).toEqual([]);result.status='passed'
} catch(e){result.error=String(e);await page.screenshot({path:artifacts+'/failure.png',fullPage:true});throw e}
finally{fs.writeFileSync(artifacts+'/browser.json',JSON.stringify(result,null,2));await browser.close()}
