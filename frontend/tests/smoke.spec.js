import {test,expect} from '@playwright/test'
import fs from 'node:fs'

test('offline workstation: replay, indicators, chart review, automated paper ledger',async({page,context})=>{
  await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort())
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  const api=async(path,body)=>{const r=await page.request[body===undefined?'get':'post'](path,body===undefined?{}:{data:body});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
  const control=body=>api('/api/smoke/control',body),evidence=()=>api('/api/smoke/evidence')
  const auto=page.getByRole('region',{name:'Paper automation'}) // section aria-label maps to region
  const ask=page.getByRole('region',{name:'Ask about chart'})
  await page.goto('/')
  await expect(page.getByText('OFFLINE SMOKETEST · constructed events and controlled provider',{exact:true}).first()).toBeVisible()
  await page.getByLabel('Mode',{exact:true}).selectOption('replay')
  await page.getByLabel('Indicator name',{exact:true}).fill('Smoke SMA')
  await page.getByLabel('Window',{exact:true}).fill('2')
  await page.getByRole('button',{name:'Add indicator',exact:true}).click()
  async function play(){await page.getByRole('button',{name:'Play replay',exact:true}).click();await expect(page.getByText('Replay complete · 6 / 6 recorded deliveries',{exact:true})).toBeVisible();await page.getByLabel('Inspect candle (UTC)',{exact:true}).selectOption({label:'2026-11-09 14:34 UTC'})}
  await play()
  const row=page.getByRole('table',{name:'Saved indicator values'}).getByRole('row').filter({hasText:'Smoke SMA'})
  await expect(row.locator('td').nth(3)).toHaveText('16') // (13+19)/2
  await page.getByLabel('Window for Smoke SMA',{exact:true}).fill('3')
  await page.getByRole('button',{name:'Save Smoke SMA window',exact:true}).click()
  await play();await expect(row.locator('td').nth(3)).toHaveText('13') // (7+13+19)/3
  await page.getByLabel('Mode',{exact:true}).selectOption('live')
  await page.getByLabel('Inspect candle (UTC)',{exact:true}).selectOption({label:'2026-11-09 14:34 UTC'})
  await ask.getByRole('button',{name:'Ask about chart',exact:true}).click()
  await expect(ask.getByRole('img',{name:'Frozen chart sent for analysis'})).toBeVisible()
  await ask.getByRole('button',{name:'Analyze frozen chart',exact:true}).click()
  await expect(ask.getByText('Status: valid',{exact:false})).toBeVisible()
  await expect(ask.getByRole('row').filter({hasText:'action'}).getByRole('cell').nth(1)).toHaveText('buy')
  await expect(ask.getByRole('row').filter({hasText:'crossover'}).getByRole('cell').nth(1)).toHaveText('up')
  await expect(ask.getByRole('row').filter({hasText:'evidence'}).getByRole('cell').nth(1)).toHaveText('sufficient')
  let saved=await evidence();expect(saved.fills).toHaveLength(0);expect(saved.calls).toHaveLength(2)
  expect(saved.calls.every(c=>c.width>=320&&c.height>=200&&c.symbol==='AAPL'&&c.candle==='2026-11-09T14:34:00Z')).toBeTruthy()
  expect(saved.calls[0].sha256).toBe(saved.calls[1].sha256)
  await control({provider_mode:'failure'})
  await ask.getByRole('button',{name:'Ask about chart',exact:true}).click()
  await ask.getByRole('button',{name:'Analyze frozen chart',exact:true}).click()
  await expect(ask.getByText('Status: provider_error',{exact:false})).toBeVisible()
  expect((await evidence()).fills).toHaveLength(0)
  await control({provider_mode:'success',order_size:4})
  await auto.getByRole('button',{name:'Start paper automation',exact:true}).click()
  await expect(auto).toContainText('Cash $1000.00 · Shares 0 · Fills 0')
  async function candle(minute,price,status='no_order'){
    await control({minute,price,complete:true})
    const stamp=`2026-11-09T14:${minute}:00Z`
    await expect.poll(async()=>{const e=await evidence();return e.jobs.find(j=>j.candle===stamp)?.status}).toBe(status)
    return (await evidence()).jobs.find(j=>j.candle===stamp)
  }
  await candle(35,7);await candle(36,1);await candle(37,13)
  const buy=await candle(38,19,'pending')
  await control({minute:39,price:100,second:10})
  await expect(auto).toContainText('Cash $600.00 · Shares 4 · Fills 1')
  await api(`/api/automation/jobs/${buy.id}/apply`,{})
  await control({duplicate:true});expect((await evidence()).fills).toHaveLength(1)
  await candle(39,100);await candle(40,1)
  await control({order_size:1})
  await candle(41,1,'pending')
  await control({minute:42,price:110,second:10})
  await expect(auto).toContainText('Cash $710.00 · Shares 3 · Fills 2')
  await candle(42,110,'skipped') // reviewer veto on real upward crossover
  expect((await evidence()).fills).toHaveLength(2)
  await expect(auto).toContainText('Reviewer: reject_unsupported_signal')
  await candle(43,1)
  await candle(44,1,'pending')
  await control({minute:45,price:105,second:10})
  await expect(auto).toContainText('Cash $1025.00 · Shares 0 · Fills 3')
  await expect(auto).toContainText('Realized P&L 25 · Unrealized 0')
  saved=await evidence();expect(saved.account.cash_cents).toBe(102500);expect(saved.account.positions[0].quantity).toBe(0)
  expect(saved.account.pnl_current.realized).toBe(25);expect(saved.account.pnl_current.unrealized).toBe(0)
  expect(saved.fills.map(f=>[f.quantity,f.price_cents])).toEqual([[4,10000],[1,11000],[3,10500]])
  const counts=[saved.orders.length,saved.fills.length,saved.jobs.length]
  await auto.getByRole('button',{name:'Stop paper automation',exact:true}).click()
  await expect(auto).toContainText('Stopped.')
  await control({minute:45,price:105,complete:true})
  // Observe the actual WebSocket view reaching the new completed candle before negative assertion.
  await page.getByLabel('Inspect candle (UTC)',{exact:true}).selectOption({label:'2026-11-09 14:45 UTC'})
  await expect(page.getByText('Ended',{exact:true})).toBeVisible()
  await page.waitForTimeout(2500) // exceeds scheduler poll period to test absence of a new job
  saved=await evidence();expect([saved.orders.length,saved.fills.length,saved.jobs.length]).toEqual(counts)
  expect(errors).toEqual([])
  await auto.screenshot({path:process.env.SMOKE_ARTIFACTS+'/account.png'})
  fs.writeFileSync(process.env.SMOKE_ARTIFACTS+'/browser-evidence.json',JSON.stringify({sma:{window2:16,window3:13},manual_fills:0,after_stop:counts,...saved},null,2))
})
