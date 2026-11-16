import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./tests',testMatch:'smoke.spec.js',workers:1,retries:0,timeout:180000,
  expect:{timeout:15000},outputDir:process.env.SMOKE_ARTIFACTS+'/browser',reporter:'list',
  use:{baseURL:process.env.SMOKE_BASE_URL,headless:!!process.env.CI || process.env.SMOKE_HEADLESS==='1',
    viewport:{width:1440,height:1000},trace:'retain-on-failure',screenshot:'only-on-failure'}})
