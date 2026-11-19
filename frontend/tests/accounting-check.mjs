// Compare actual Vue/API values against independently inspected SQLite rows.
import {chromium,expect} from '@playwright/test'
import fs from 'node:fs'
const expected=JSON.parse(fs.readFileSync(process.env.ACCOUNTING_EXPECTED,'utf8'))
const browser=await chromium.launch({headless:true})
const page=await browser.newPage({baseURL:process.env.ACCOUNTING_URL,viewport:{width:1600,height:1100}})
const money=value=>value==null?'Unavailable':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value)
const result={status:'failed',case:process.env.ACCOUNTING_CASE,phase:process.env.ACCOUNTING_PHASE}
try{
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 await page.goto('/')
 const panel=page.getByRole('region',{name:'Local paper account'})
 await expect(panel.getByText(`Account: live · live`,{exact:true})).toBeVisible()
 const response=await page.request.get('/api/paper/account')
 expect(response.ok()).toBe(true)
 const api=await response.json()
 expect(api.pnl_history).toEqual(expected.rows)
 expect(api.cash_cents).toBe(expected.cash_cents)
 expect(api.orders).toEqual(expected.orders);expect(api.fills).toEqual(expected.fills)
 const rows=panel.getByRole('table',{name:'Profit and loss history'}).locator('tbody tr')
 await expect(rows).toHaveCount(expected.rows.length)
 const displayed=[]
 for(let i=0;i<expected.rows.length;i++){
  const row=expected.rows[i],cells=rows.nth(i).locator('td')
  const values=[money(row.cash_cents/100),String(row.quantity),row.average_cost==null?'—':money(row.average_cost),money(row.price),money(row.realized),money(row.unrealized),money(row.total)]
  for(let j=0;j<values.length;j++)await expect(cells.nth(j+2)).toHaveText(values[j])
  displayed.push(values)
 }
 if(process.env.ACCOUNTING_CASE==='unavailable'){
  await expect(panel.getByText('Open-position valuation unavailable: no usable valuation price.',{exact:true})).toBeVisible()
  await expect(panel).toContainText('Unrealized: Unavailable · Total P&L: Unavailable')
 }
 // Repeat reads: neither market observations nor accounting events may multiply.
 expect((await (await page.request.get('/api/paper/account')).json()).pnl_history).toEqual(api.pnl_history)
 await panel.screenshot({path:process.env.ACCOUNTING_OUTPUT+'.png'})
 result.status='passed';result.api=api;result.displayed=displayed
} catch(e){result.error=String(e);await page.screenshot({path:process.env.ACCOUNTING_OUTPUT+'-failure.png',fullPage:true});throw e}
finally{fs.writeFileSync(process.env.ACCOUNTING_OUTPUT+'.json',JSON.stringify(result,null,2)+'\n');await browser.close()}
