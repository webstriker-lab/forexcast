import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/accuracy')
})

test('accuracy page loads with heading', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Prediction Accuracy' })).toBeVisible()
})

test('summary strip is visible', async ({ page }) => {
  // Summary strip contains "of" and "pairs" — present whether data exists or not
  await expect(page.getByText(/\d+ of \d+ pairs|No backtest stats/)).toBeVisible({ timeout: 10000 })
})

test('horizon tabs 7d/30d/90d/365d all render', async ({ page }) => {
  for (const label of ['7d', '30d', '90d', '365d']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
})

test('clicking 30d tab activates it', async ({ page }) => {
  await page.getByRole('button', { name: '30d' }).click()
  const btn = page.getByRole('button', { name: '30d' })
  await expect(btn).toHaveClass(/bg-blue-600/)
})
