// Focused real-browser SMA verification, driven by docs/sma_check.py.
import {chromium, expect} from '@playwright/test'
import fs from 'node:fs'
const browser = await chromium.launch({headless:true})
const page = await browser.newPage({viewport:{width:1440,height:1100}})
const expected = [[null,null,null],[11.5,null,null],[8.5,10,null],[10,10,null],[16,13,'up'],[13,13,null],[4,9,'down']]
const errors=[]
page.on('pageerror',e=>errors.push(e.message))
const output={expected, observed:[], checks:[]}
const artifacts=process.env.SMA_ARTIFACTS
try {
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
  await page.goto(process.env.SMA_BASE_URL)
  await expect(page.getByRole('list',{name:'Confirmed SMA crossovers'}).locator('li')).toHaveCount(2)
  await page.getByLabel('Mode',{exact:true}).selectOption('replay')
  await expect(page.getByText('Replay ready · 0 / 7 recorded deliveries',{exact:true})).toBeVisible()
  for(let step=1;step<=7;step++) {
    const response=page.waitForResponse(r=>r.url().includes('/api/replay?')&&new URL(r.url()).searchParams.get('step')===String(step))
    await page.getByRole('button',{name:'Next observation',exact:true}).click()
    const view=await (await response).json()
    expect(view.sma.values.map(r=>[r.short,r.long,r.signal])).toEqual(expected.slice(0,step))
    await expect(page.getByText(`Replay ${step===7?'complete':'ready'} · ${step} / 7 recorded deliveries`,{exact:true})).toBeVisible()
    await page.getByLabel('Inspect candle (UTC)',{exact:true}).selectOption({label:`2026-11-09 14:${29+step} UTC`})
    for(const [label,value] of [['Short SMA',expected[step-1][0]],['Long SMA',expected[step-1][1]],['Crossover',expected[step-1][2]||'None']]) {
      await expect(page.locator('.inspection dt').filter({hasText:new RegExp(`^${label}$`)}).locator('..').locator('dd')).toHaveText(value===null?'Unavailable':String(value))
    }
    output.observed.push(view.sma.values)
  }
  const markers=page.getByRole('list',{name:'Confirmed SMA crossovers'})
  await expect(markers).toContainText('14:34:00Z · SMA up · Short 16 / Long 13')
  await expect(markers).toContainText('14:36:00Z · SMA down · Short 4 / Long 9')
  await page.locator('.chart').screenshot({path:artifacts+'/sma-chart.png'})
  await page.screenshot({path:artifacts+'/sma-page.png',fullPage:true})
  output.checks.push('All seven replay prefixes and inspector values match hand reference; two confirmed markers')
  // Native HTML constraints catch zero/fractions; Vue catches equal/reversed windows.
  for(const [short,long,native] of [['0','3',true],['1.5','3',true],['3','3',false],['4','3',false]]) {
    await page.getByLabel('Short SMA',{exact:true}).fill(short)
    await page.getByLabel('Long SMA',{exact:true}).fill(long)
    await page.getByRole('button',{name:'Apply SMA windows',exact:true}).click()
    if(native) expect(await page.locator('#short-sma').evaluate(e=>e.validity.valid)).toBe(false)
    else await expect(page.getByText('Use positive whole numbers with short smaller than long.',{exact:true})).toBeVisible()
    await expect(markers.locator('li')).toHaveCount(2)
  }
  await page.getByLabel('Short SMA',{exact:true}).fill('3')
  await page.getByLabel('Long SMA',{exact:true}).fill('5')
  await page.getByRole('button',{name:'Apply SMA windows',exact:true}).click()
  await expect(page.getByText('Replay ready · 0 / 7 recorded deliveries',{exact:true})).toBeVisible()
  await expect(markers.locator('li')).toHaveCount(0)
  await page.getByRole('button',{name:'Play replay',exact:true}).click()
  await expect(page.getByText('Replay complete · 7 / 7 recorded deliveries',{exact:true})).toBeVisible({timeout:15000})
  await expect(page.getByText('Blue: short SMA (3). Purple: long SMA (5).',{exact:false})).toBeVisible()
  output.checks.push('Invalid windows rejected without replacing data; valid 3/5 resets replay and removes stale markers')
  for(const query of ['short=0&long=3','short=1.5&long=3','short=3&long=3']) {
    const r=await page.request.get(process.env.SMA_BASE_URL+'/api/history?'+query)
    expect(r.status()).toBe(422)
  }
  expect(errors).toEqual([])
  output.status='passed'
} catch(e) {
  output.status='failed';output.error=String(e)
  await page.screenshot({path:artifacts+'/failure.png',fullPage:true})
  throw e
} finally {
  fs.writeFileSync(artifacts+'/browser.json',JSON.stringify(output,null,2)+'\n')
  await browser.close()
}
