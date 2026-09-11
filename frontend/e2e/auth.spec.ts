import { expect, test } from '@playwright/test'

test('renders the sign-in screen for unauthenticated users', async ({ page }) => {
  await page.goto('/')

  await expect(
    page.getByRole('heading', { name: 'Sign in to your agent workspace.' }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: 'Sign in with Microsoft' }),
  ).toBeVisible()
})
