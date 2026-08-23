import * as fs from 'fs'
import * as path from 'path'
import { chromium, type FullConfig } from '@playwright/test'

export default async function globalSetup(_config: FullConfig) {
  const email = process.env.VITE_TEST_EMAIL
  const password = process.env.VITE_TEST_PASSWORD
  if (!email || !password) {
    throw new Error(
      'VITE_TEST_EMAIL and VITE_TEST_PASSWORD must be set in frontend/.env.test before running E2E tests',
    )
  }

  const browser = await chromium.launch()
  const page = await browser.newPage()

  await page.goto('http://localhost:5173/login')
  await page.fill('#email', email)
  await page.fill('#password', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard', { timeout: 15000 })

  const authDir = path.resolve(__dirname, '.auth')
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true })
  await page.context().storageState({ path: path.join(authDir, 'user.json') })

  await browser.close()
}
