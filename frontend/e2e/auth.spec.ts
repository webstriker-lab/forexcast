import { test, expect } from '@playwright/test'

// Override the global storageState so these tests run unauthenticated
test.use({ storageState: { cookies: [], origins: [] } })

test('login page has email and password fields', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('#email')).toBeVisible()
  await expect(page.locator('#password')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
})

test('valid credentials redirect to dashboard', async ({ page }) => {
  await page.goto('/login')
  await page.fill('#email', process.env.VITE_TEST_EMAIL!)
  await page.fill('#password', process.env.VITE_TEST_PASSWORD!)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard', { timeout: 15000 })
  await expect(page).toHaveURL(/dashboard/)
})

test('unauthenticated /dashboard visit redirects to /login', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/login/)
})
