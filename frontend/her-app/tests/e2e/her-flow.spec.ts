import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(60000)

const bindPhone = process.env.HER_E2E_BIND_PHONE || '13800138004'

async function launchToWelcome(page: import('@playwright/test').Page) {
  await page.context().clearCookies()
  await page.goto('http://127.0.0.1:3000/splash')
  await page.evaluate(() => {
    window.localStorage.clear()
  })
  await page.reload()
  const startButton = page.getByRole('button', { name: '开始了解' })
  await expect(startButton).toBeVisible({ timeout: 10000 })
  await startButton.click()
  await expect(page).toHaveURL(/\/welcome/)
  await expect(page.getByRole('button', { name: '手机号登录' })).toBeVisible()
}

async function fillVerificationCode(page: import('@playwright/test').Page) {
  let code = ''
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
      if (code.length === 6) break
    } catch {
      // stub gateway writes code asynchronously
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

/** Ensure login session has profile/requester IDs (via /auth/me or onboarding PATCH). */
async function ensureSessionProfile(page: import('@playwright/test').Page) {
  await page
    .waitForResponse(
      (response) =>
        response.url().includes('/api/gateway/v1/auth/me') && response.status() === 200,
      { timeout: 20000 },
    )
    .catch(() => null)

  const linked = await page.evaluate(() => {
    try {
      const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
      return Boolean(ctx.profileLinked || (ctx.requesterId && ctx.profileId))
    } catch {
      return false
    }
  })
  if (linked) return

  await page.evaluate(async () => {
    const token = window.localStorage.getItem('her_demo_access_token')
    if (!token) return
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
    if (!res.ok) return
    const data = (await res.json()) as { profile_id?: number; requester_id?: number }
    const profileId = data.profile_id ?? data.requester_id
    if (!profileId) return
    const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
    ctx.requesterId = profileId
    ctx.profileId = profileId
    ctx.profileLinked = true
    window.localStorage.setItem('her_session_context', JSON.stringify(ctx))
  })
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

test('sms auth + discovery + recommendation action hit real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '手机号登录' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  const sendCodeRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/auth/sms/send-code') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '获取验证码' }).click()
  await sendCodeRequest
  await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
  await expect(page.getByText('输入验证码')).toBeVisible()
  await fillVerificationCode(page)
  await page.waitForURL(/\/(discover|onboarding)/, { timeout: 20000 })
  await ensureSessionProfile(page)
  if (!page.url().includes('/discover')) {
    await page.goto('http://127.0.0.1:3000/discover')
  }
  await expect(page).toHaveURL(/\/discover/, { timeout: 15000 })

  expect(Array.from(hits)).toEqual(
    expect.arrayContaining([
      'POST /v1/auth/sms/send-code',
      'POST /v1/auth/sms/verify-code',
      'GET /v1/auth/me',
    ]),
  )

  const composer = page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/)
  await expect(composer).toBeVisible({ timeout: 15000 })

  await page.waitForTimeout(1500)
  const turnRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/discovery/sessions/') && request.method() === 'POST',
    { timeout: 20000 },
  )
  await composer.fill('我在无锡，想找认真恋爱的人')
  await page.getByRole('button', { name: '发送消息' }).click()
  await turnRequest

  await page.getByRole('button', { name: '来信' }).click()
  await expect(page.getByText('推荐来信')).toBeVisible()
  const actionRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/recommendation/actions') &&
      request.method() === 'POST',
  )
  await page.locator('button[aria-label^="收藏"]').first().click()
  await actionRequest

  expect(Array.from(hits).some((item) => item.startsWith('POST /v1/discovery/sessions'))).toBe(true)
  expect(Array.from(hits).some((item) => item === 'POST /v1/recommendation/actions')).toBe(true)
})

test('wechat login hits real backend (bind phone when required)', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const loginRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/auth/wechat/login') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '微信登录' }).click()
  await loginRequest

  const bindButton = page.getByRole('button', { name: '绑定手机号' })
  if (await bindButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await bindButton.click()
    await page.getByPlaceholder('请输入手机号').fill(bindPhone)
    await page.getByRole('button', { name: '获取验证码' }).click()
    await expect(page.getByText('输入验证码')).toBeVisible()
    await fillVerificationCode(page)
  }

  await expect(page).toHaveURL(/\/(discover|onboarding|wechat)/, { timeout: 15000 })

  expect(Array.from(hits)).toEqual(expect.arrayContaining(['POST /v1/auth/wechat/login']))
  if (Array.from(hits).includes('POST /v1/auth/wechat/bind-phone')) {
    expect(Array.from(hits)).toEqual(
      expect.arrayContaining(['POST /v1/auth/sms/send-code', 'POST /v1/auth/wechat/bind-phone']),
    )
  }
})

test('one-tap login success hits real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const createRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/auth/one-tap/create') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '本机号码一键登录' }).click()
  await createRequest
  await expect(page).toHaveURL(/\/login\/one-tap/, { timeout: 15000 })
  const verifyRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/auth/one-tap/verify') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '一键登录' }).click()
  await verifyRequest
  await expect(page).toHaveURL(/\/discover/, { timeout: 15000 })

  expect(Array.from(hits)).toEqual(expect.arrayContaining([
    'POST /v1/auth/one-tap/create',
    'POST /v1/auth/one-tap/verify',
  ]))
})

test('relationships and chat pages hit real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const demoToggle = page.locator('button.fixed.bottom-6.right-6')
  await demoToggle.click()
  const timelineRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v2/chat/cases/case-frontend-demo/timeline') && request.method() === 'GET')
  await page.getByRole('button', { name: '关系' }).click()
  await timelineRequest
  await expect(page.getByRole('heading', { name: '关系' })).toBeVisible()
  const activeRelationship = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: '正在进行中' }) })
    .getByRole('button')
    .first()
  await expect(activeRelationship).toBeVisible({ timeout: 15000 })
  await activeRelationship.click()
  await page.getByPlaceholder('输入消息...').fill('前端联调消息')
  await page.getByRole('button', { name: '发送消息' }).click()
  await page.waitForTimeout(1500)

  expect(Array.from(hits)).toEqual(expect.arrayContaining([
    'GET /v2/chat/cases/case-frontend-demo/timeline',
    expect.stringContaining('GET /v2/chat/conversations/'),
    expect.stringContaining('GET /v2/chat/conversations/'),
    expect.stringContaining('POST /v2/chat/conversations/'),
  ]))
})
