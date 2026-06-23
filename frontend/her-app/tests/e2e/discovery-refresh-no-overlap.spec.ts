import { expect, test } from '@playwright/test'
test.setTimeout(120000)

const bindPhone = process.env.HER_E2E_BIND_PHONE || '13800138004'
const fixedCode = '123456'

async function launchToWelcome(page: import('@playwright/test').Page) {
  await page.context().clearCookies()
  await page.goto('http://127.0.0.1:3000/splash')
  await page.evaluate(() => {
    window.localStorage.clear()
  })
  await page.reload()
  await expect(page.getByRole('button', { name: '开始了解' })).toBeVisible({ timeout: 10000 })
  await page.getByRole('button', { name: '开始了解' }).click()
  await expect(page).toHaveURL(/\/welcome/)
  await expect(page.getByRole('button', { name: '使用其他手机号' })).toBeVisible()
}

async function fillVerificationCode(page: import('@playwright/test').Page) {
  const inputs = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < fixedCode.length; i += 1) {
    await inputs.nth(i).fill(fixedCode[i])
  }
}

async function ensureSessionProfile(page: import('@playwright/test').Page) {
  const ready = await page.evaluate(async () => {
    const token = window.localStorage.getItem('her_demo_access_token')
    if (!token) return false

    const syncMe = async () => {
      const meRes = await fetch('/api/gateway/v1/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
        credentials: 'include',
      })
      if (!meRes.ok) return false
      const me = (await meRes.json()) as {
        user?: { profile_id?: number; requester_id?: number; user_id?: string }
      }
      const profileId = me.user?.profile_id
      const requesterId = me.user?.requester_id ?? profileId
      if (!profileId || !requesterId) return false
      const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
      ctx.requesterId = requesterId
      ctx.profileId = profileId
      ctx.profileLinked = true
      ctx.userId = me.user?.user_id ?? ctx.userId
      window.localStorage.setItem('her_session_context', JSON.stringify(ctx))
      return true
    }

    if (await syncMe()) return true

    const res = await fetch('/api/gateway/v1/auth/onboarding', {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({
        basic_info: {
          name: 'E2E用户',
          birthday: '1995-01-01',
          gender: 'female',
          location: '无锡',
          relationship_goal: 'long_term',
        },
        preference: {
          relationship_goal: 'long_term',
          tags: ['阅读', '旅行', '美食'],
        },
        mark_completed: true,
      }),
    })
    if (!res.ok) return false
    return syncMe()
  })

  if (!ready) {
    throw new Error('E2E: could not link requester/profile for discovery')
  }
}

async function extractCurrentCandidateIds(page: import('@playwright/test').Page): Promise<string[]> {
  return page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button[aria-label^="查看候选人 "]'))
    const ids: string[] = []
    for (const button of buttons) {
      const text = button.textContent || ''
      const match = text.match(/(\d{3,})/)
      if (match) ids.push(match[1])
    }
    return ids
  })
}

test('discovery refresh should fully exclude previous batch on frontend', async ({ page }) => {
  await launchToWelcome(page)
  await page.getByRole('button', { name: '使用其他手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill(bindPhone)
  const sendCodeRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/auth/sms/send-code') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '获取验证码' }).click()
  await sendCodeRequest
  await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
  await expect(page.getByText('输入验证码')).toBeVisible()
  await fillVerificationCode(page)
  await expect(page).toHaveURL(/\/(discover|onboarding)/, { timeout: 20000 })

  await ensureSessionProfile(page)
  await page.goto('http://127.0.0.1:3000/discover')

  await page.waitForResponse(
    (response) =>
      response.url().includes('/api/gateway/v1/discovery/sessions') &&
      response.request().method() === 'POST' &&
      response.status() < 400,
    { timeout: 30000 },
  ).catch(() => null)

  await page.waitForTimeout(5000)

  const firstBatch = await extractCurrentCandidateIds(page)
  expect(firstBatch.length).toBeGreaterThan(0)

  const refreshButton = page
    .getByRole('button', { name: /换一批|看看更多|看看其他人/ })
    .first()
  await expect(refreshButton).toBeVisible({ timeout: 15000 })

  const refreshResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes('/api/gateway/v1/discovery/sessions/') &&
      response.request().method() === 'POST' &&
      response.status() < 400,
    { timeout: 30000 },
  )

  await refreshButton.click()
  await refreshResponsePromise.catch(() => null)
  await page.waitForTimeout(5000)

  const secondBatch = await extractCurrentCandidateIds(page)
  expect(secondBatch.length).toBeGreaterThan(0)

  const overlap = firstBatch.filter((id) => secondBatch.includes(id))

  console.log('firstBatch=', firstBatch)
  console.log('secondBatch=', secondBatch)
  console.log('overlap=', overlap)

  expect(overlap).toEqual([])
})
