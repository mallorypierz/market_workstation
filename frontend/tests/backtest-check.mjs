import {chromium,expect} from '@playwright/test'
import fs from 'node:fs'
const phase=process.env.BT_PHASE,out=process.env.BT_OUT
const browser=await chromium.launch({headless:true}),page=await browser.newPage({baseURL:process.env.BT_URL,viewport:{width:1450,height:1100}})
const errors=[];page.on('pageerror',e=>errors.push(String(e)))
try{
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 if(phase!=='before'){const saved=JSON.parse(fs.readFileSync(out+'/response.json'));await page.addInitScript(id=>localStorage.setItem('backtest-id',id),saved.run_id)}
 await page.goto('/');const p=page.getByRole('region',{name:'Historical backtest'})
 if(phase==='failure'){await expect(p.getByRole('alert')).toContainText('Backend unavailable');await p.screenshot({path:out+'/failure.png'});}
 else{
 if(phase==='before'){
  await p.getByLabel('Dataset',{exact:true}).selectOption('aapl-2025-daily')
  await p.getByLabel('Short window').fill('3');await p.getByRole('button',{name:'Run new backtest'}).click();await expect(p.getByRole('alert')).toContainText('short < long')
  await p.getByLabel('Short window').fill('2')
  await p.getByLabel('Evaluation start UTC').fill('2026-01-01T00:00:00Z');await p.getByLabel('End exclusive UTC').fill('2026-02-01T00:00:00Z');await p.getByRole('button',{name:'Run new backtest'}).click();await expect(p.getByRole('alert')).toContainText('No completed evaluation candles')
  await p.screenshot({path:out+'/empty.png'})
  await p.getByLabel('Dataset',{exact:true}).selectOption('recorded');await p.getByLabel('Dataset',{exact:true}).selectOption('aapl-2025-daily')
  await p.getByRole('button',{name:'Run new backtest'}).click()
 }
 await expect(p.getByRole('status')).toContainText('completed',{timeout:30000})
 await expect(p).toContainText('Cash $999.64');await expect(p).toContainText('Realized -$0.36 · Unrealized $0.00')
 const rows=p.getByRole('table',{name:'Backtest decisions'}).locator('tbody tr');await expect(rows).toHaveCount(33)
 await expect(rows.nth(2)).toContainText('up');await expect(rows.nth(3)).toContainText('down')
 await rows.nth(2).locator('summary').click();await expect(rows.nth(2)).toContainText('2025-01-16T14:30:00Z')
 const id=await page.evaluate(()=>localStorage.getItem('backtest-id'));const response=await(await page.request.get('/api/backtests/'+id)).json()
 expect(response.result.chart.sma.values.filter(v=>v.signal).length).toBeGreaterThan(1)
 if(phase==='before')fs.writeFileSync(out+'/response.json',JSON.stringify(response,null,2));else expect(response).toEqual(JSON.parse(fs.readFileSync(out+'/response.json')))
 await p.screenshot({path:out+'/'+phase+'.png'})
 if(phase==='before'){
  await p.getByLabel('End exclusive UTC').fill('2025-01-16T00:00:00Z');await p.getByRole('button',{name:'Run new backtest'}).click()
  await expect(p).toContainText('1 pending orders');await expect(p.getByRole('table',{name:'Backtest decisions'})).toContainText('#1 pending → No fill')
  await p.screenshot({path:out+'/pending.png'})
  await p.getByLabel('Saved run',{exact:true}).selectOption(id);await p.getByRole('button',{name:'Load saved result',exact:true}).click();await expect(p).toContainText('Cash $999.64')
 }
 await page.reload();await expect(p.getByRole('status')).toContainText('completed');await expect(p).toContainText('Cash $999.64')
 const invalid=await page.request.post('/api/backtests',{data:{run_id:'bad',start:'2025-01-01T00:00:00Z',end:'2025-02-01T00:00:00Z',short:1.5}});expect(invalid.status()).toBe(422)
 expect(errors).toEqual([])
 }
 fs.writeFileSync(out+'/'+phase+'.json',JSON.stringify({status:'passed',phase,errors},null,2))
}finally{await browser.close()}
