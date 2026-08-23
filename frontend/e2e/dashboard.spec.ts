import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/dashboard')
})

test('pair picker renders with Add button', async ({ page }) => {
  await expect(page.getByRole('button', { name: '+ Add' })).toBeVisible()
})

test('adding EUR/USD shows a recommendation card', async ({ page }) => {
  // USD is already the default base; set quote to EUR
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  // Wait for one of the four valid recommendation states
  await expect(
    page.getByText(/ACT NOW|WAIT|VOLATILE|NO SIGNAL/),
  ).toBeVisible({ timeout: 15000 })
})

test('rate chart canvas renders after pair is added', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await expect(page.locator('canvas')).toBeVisible({ timeout: 15000 })
})

test('"Predict for a specific date" section is visible after pair is added', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await expect(page.getByText('Predict for a specific date')).toBeVisible({ timeout: 15000 })
})

test('selecting a date 14 days from today shows interpolated prediction card', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await page.getByText('Predict for a specific date').waitFor({ timeout: 15000 })

  const target = new Date()
  target.setDate(target.getDate() + 14)
  const dateStr = target.toISOString().split('T')[0]

  await page.fill('input[type="date"]', dateStr)
  // The card shows a 4-decimal rate value
  await expect(page.locator('text=/\\d+\\.\\d{4}/')).toBeVisible({ timeout: 10000 })
})
