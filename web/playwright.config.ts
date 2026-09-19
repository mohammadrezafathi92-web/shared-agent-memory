import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./tests',fullyParallel:false,workers:1,retries:0,reporter:'list',use:{baseURL:process.env.MEMORY_E2E_URL||'http://127.0.0.1:8765',headless:true,trace:'off'},timeout:30000})
