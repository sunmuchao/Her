import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(90000)

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
}

async function fillVerificationCode(page: import('@playwright/test').Page) {
  let code = ''
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
      if (code.length === 6) break
    } catch {
      // SMS stub writes asynchronously.
    }
    await page.waitForTimeout(200)
  }
  if (code.length !== 6) {
    throw new Error('SMS stub code file not ready at /tmp/her_sms_code.txt')
  }
  const inputs = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < code.length; i += 1) {
    await inputs.nth(i).fill(code[i])
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
    throw new Error('E2E: could not link requester/profile for values auction')
  }
}

function trackGatewayRequests(page: import('@playwright/test').Page) {
  const hits = new Set<string>()
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/gateway/')) return
    const path = url.pathname.replace('/api/gateway', '')
    hits.add(`${request.method()} ${path}`)
  })
  return hits
}

test('values auction single-player flow hits real backend and renders all cards', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '使用其他手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
  await fillVerificationCode(page)
  await page.waitForURL(/\/(discover|onboarding)/, { timeout: 20000 })
  await ensureSessionProfile(page)

  await page.goto('http://127.0.0.1:3000/discover')
  await expect(page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/)).toBeVisible({ timeout: 20000 })

  await page.getByRole('button', { name: '展开菜单' }).click()
  await page.getByRole('button', { name: '心理测评' }).click()
  await expect(page.getByRole('button', { name: '价值观拍卖会' })).toBeVisible()

  const startRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/values-auction/start') && request.method() === 'POST',
    { timeout: 15000 },
  )
  await page.getByRole('button', { name: '价值观拍卖会' }).click()
  await startRequest
  await expect(page.getByRole('heading', { name: /价值观拍卖/ })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: '开始拍卖' })).toBeVisible()

  const traitsRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/values-auction/traits') && request.method() === 'POST',
    { timeout: 15000 },
  )
  await page.getByRole('button', { name: '开始拍卖' }).click()
  await traitsRequest
  await expect(page.getByText('分配你的筹码')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(/剩余 10 筹码/)).toBeVisible()

  const plusButtons = page.locator('button').filter({ hasText: '+' })
  await plusButtons.nth(0).click()
  await plusButtons.nth(0).click()
  await plusButtons.nth(1).click()
  await plusButtons.nth(1).click()
  await plusButtons.nth(2).click()
  await plusButtons.nth(2).click()
  await plusButtons.nth(3).click()
  await plusButtons.nth(3).click()
  await plusButtons.nth(4).click()
  await plusButtons.nth(4).click()
  await expect(page.getByText('确认分配')).toBeVisible({ timeout: 10000 })

  const submitRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/values-auction/submit') && request.method() === 'POST',
    { timeout: 15000 },
  )
  await page.getByRole('button', { name: '确认分配' }).click()
  await submitRequest
  await expect(page.getByRole('heading', { name: '拍卖完成！' })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: '查看AI解读' })).toBeVisible()

  const interpretationRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/values-auction/interpretation') &&
      request.method() === 'POST',
    { timeout: 15000 },
  )
  await page.getByRole('button', { name: '查看AI解读' }).click()
  await interpretationRequest
  await expect(page.getByRole('heading', { name: 'AI 价值观解读' })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: '继续聊天' })).toBeVisible()

  expect(Array.from(hits)).toEqual(
    expect.arrayContaining([
      'POST /v1/auth/sms/send-code',
      'POST /v1/auth/sms/verify-code',
      'GET /v1/auth/me',
      'POST /v1/values-auction/start',
      'POST /v1/values-auction/traits',
      'POST /v1/values-auction/submit',
      'POST /v1/values-auction/interpretation',
    ]),
  )
})
