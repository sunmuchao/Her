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
  await expect(page.getByRole('button', { name: '使用其他手机号' })).toBeVisible()
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

  await page.goto('http://127.0.0.1:3000/discover')
  await page
    .waitForResponse(
      (response) =>
        response.url().includes('/api/gateway/v1/discovery/sessions') &&
        response.request().method() === 'POST' &&
        response.status() < 400,
      { timeout: 25000 },
    )
    .catch(() => null)
}

const E2E_PROFILE_SOURCE =
  'mysql://root@127.0.0.1:3307/her?table=profiles&photos_table=profile_photos'

/** Create subscription + refresh; ensure recommendation action can hit backend. */
async function ensureRecommendationCard(page: import('@playwright/test').Page) {
  const seeded = await page.evaluate(async (profileSource: string) => {
    const token = window.localStorage.getItem('her_demo_access_token')
    const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
    const profileId = ctx.profileId
    if (!token || !profileId) return { ok: false, reason: 'missing token or profileId' }

    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    }

    const hasActionableCard = async () => {
      const res = await fetch(
        `/api/gateway/v1/recommendation/cards?profile_id=${profileId}`,
        { headers, credentials: 'include' },
      )
      if (!res.ok) return false
      const data = (await res.json()) as {
        cards?: Array<{ subscription_id?: string; candidate_id?: number }>
      }
      return (data.cards || []).some((card) => card.subscription_id && card.candidate_id)
    }

    const postSaveAction = async (subscriptionId: string, candidateId: number) => {
      const idem = `e2e-${subscriptionId}-${candidateId}-save`
      const res = await fetch('/api/gateway/v1/recommendation/actions', {
        method: 'POST',
        headers: { ...headers, 'Idempotency-Key': idem },
        credentials: 'include',
        body: JSON.stringify({
          subscription_id: subscriptionId,
          candidate_id: candidateId,
          action_type: 'save',
          client_idempotency_key: idem,
        }),
      })
      return res.ok
    }

    if (await hasActionableCard()) return { ok: true }

    const subRes = await fetch('/api/gateway/v1/recommendation/subscriptions', {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({
        requester_id: profileId,
        source: profileSource,
        criteria: {
          gender: '女',
          cities: ['无锡', '上海'],
          relationship_goals: ['认真恋爱', '结婚导向'],
        },
        self_profile: { age: 30, city: '无锡', education: '本科' },
        limit_count: 5,
        top_k: 5,
        min_notify_score: 1,
        daily_notification_cap: 5,
        quiet_hours_start: 23,
        quiet_hours_end: 8,
        refresh_interval_hours: 24,
        recommendation_mode: 'match_based',
        title: 'E2E推荐订阅',
        now: '2026-05-07 10:00:00',
      }),
    })
    if (!subRes.ok) {
      return { ok: false, reason: `subscription ${subRes.status}: ${await subRes.text()}` }
    }
    const subData = (await subRes.json()) as { subscription?: { subscription_id?: string } }
    const subscriptionId = subData.subscription?.subscription_id
    if (!subscriptionId) return { ok: false, reason: 'subscription id missing in response' }

    const refreshRes = await fetch(
      `/api/gateway/v1/recommendation/subscriptions/${subscriptionId}/refresh`,
      {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({ now: '2026-05-07 10:05:00' }),
      },
    )
    if (!refreshRes.ok) {
      return { ok: false, reason: `refresh ${refreshRes.status}: ${await refreshRes.text()}` }
    }
    const refreshData = (await refreshRes.json()) as { result_count?: number }

    const recRes = await fetch(
      `/api/gateway/v1/recommendation/subscriptions/${subscriptionId}/recommendations`,
      { headers, credentials: 'include' },
    )
    if (recRes.ok) {
      const recData = (await recRes.json()) as {
        recommendations?: Array<{ candidate_id?: number }>
      }
      const candidateId = recData.recommendations?.[0]?.candidate_id
      if (candidateId && (await postSaveAction(subscriptionId, candidateId))) {
        return { ok: true }
      }
    }

    for (let i = 0; i < 40; i += 1) {
      if (await hasActionableCard()) return { ok: true }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }

    if (typeof refreshData.result_count === 'number') {
      return { ok: true, reason: `refresh ok (result_count=${refreshData.result_count})` }
    }

    return { ok: false, reason: 'no actionable card after refresh' }
  }, E2E_PROFILE_SOURCE)

  if (typeof seeded !== 'object' || !seeded?.ok) {
    const reason = typeof seeded === 'object' && seeded && 'reason' in seeded ? String(seeded.reason) : 'unknown'
    throw new Error(`E2E: could not seed recommendation card for inbox action (${reason})`)
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

test('sms auth + discovery + recommendation action hit real backend', async ({ page }) => {
  test.setTimeout(90000)
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '使用其他手机号' }).click()
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

  await ensureRecommendationCard(page)

  expect(Array.from(hits).some((item) => item.startsWith('POST /v1/discovery/sessions'))).toBe(true)
  expect(Array.from(hits).some((item) => item.startsWith('POST /v1/recommendation/subscriptions'))).toBe(
    true,
  )
  expect(
    Array.from(hits).some((item) => item.includes('/v1/recommendation/subscriptions/') && item.includes('/refresh')),
  ).toBe(true)

  const saveButton = page.locator('button[aria-label^="收藏"]').first()
  if (await saveButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    const actionRequest = page.waitForRequest(
      (request) =>
        request.url().includes('/api/gateway/v1/recommendation/actions') &&
        request.method() === 'POST',
      { timeout: 15000 },
    )
    await page.getByRole('button', { name: '来信' }).click()
    await expect(page.getByText('推荐来信')).toBeVisible()
    await saveButton.click()
    await actionRequest
    expect(Array.from(hits).some((item) => item === 'POST /v1/recommendation/actions')).toBe(true)
  }
})

test('wechat login hits real backend (bind phone when required)', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const loginRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/auth/wechat/login') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '使用微信登录' }).click()
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
  test.setTimeout(60000)
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const createRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/auth/one-tap/create') && request.method() === 'POST',
  )
  const verifyRequest = page.waitForRequest(
    (request) => request.url().includes('/api/gateway/v1/auth/one-tap/verify') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '一键登录' }).click()
  await createRequest
  await verifyRequest
  await expect(page).toHaveURL(/\/(discover|onboarding|welcome|wechat)/, { timeout: 20000 })

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
  await expect(page.getByRole('heading', { name: '关系' })).toBeVisible({ timeout: 15000 })
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
