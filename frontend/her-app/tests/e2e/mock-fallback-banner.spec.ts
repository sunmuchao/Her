import { expect, test } from '@playwright/test'

/**
 * Dev-only regression: when MOCK_FALLBACK is enabled, pages must show DemoDataBanner.
 * CI job `mock-fallback-regression` runs this with NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=true.
 */
test.describe('mock fallback banner @mock-fallback', () => {
  test.skip(
    process.env.NEXT_PUBLIC_ALLOW_MOCK_FALLBACK !== 'true',
    'requires NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=true',
  )

  test('profile page shows demo banner when mock fallback is on and user is logged out', async ({
    page,
  }) => {
    await page.goto('/splash')
    await page.evaluate(() => window.localStorage.clear())
    await page.goto('/profile')
    await expect(page.getByText('当前展示的是演示数据')).toBeVisible({ timeout: 15000 })
  })
})
