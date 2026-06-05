import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(90000)
const PARTNER_KEY = '9453'

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
  })

  if (!ready) {
    throw new Error('E2E: could not link requester/profile for dual values auction')
  }
}

async function getCurrentProfileId(page: import('@playwright/test').Page): Promise<string> {
  const profileId = await page.evaluate(() => {
    const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
    return ctx.profileId ? String(ctx.profileId) : ''
  })
  if (!profileId) {
    throw new Error('E2E: missing current profile id for dual values auction')
  }
  return profileId
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

async function assignCurrentLot(page: import('@playwright/test').Page, label: string) {
  if (label === '0 筹码') {
    await page.getByRole('button', { name: '这件不投' }).click()
    return
  }
  await page.getByRole('button', { name: label }).click()
  await page.getByRole('button', { name: /锁定这件|进入封盘前调整/ }).click()
}

test('chat page exposes dual values auction entry and hits start-together', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '使用其他手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
  await fillVerificationCode(page)
  await page.waitForURL(/\/(discover|onboarding)/, { timeout: 20000 })
  await ensureSessionProfile(page)

  await page.goto(
    'http://127.0.0.1:3000/chat/demo?caseId=case-frontend-demo&counterpartId=9453&chatTitle=测试对象',
  )
  await expect(page.getByPlaceholder('输入消息...')).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '展开菜单' }).click()
  const dualEntry = page.getByRole('button', { name: '双人价值观拍卖' })
  await expect(dualEntry).toBeVisible()

  const startTogetherRequest = page.waitForRequest(
    (request) =>
      request.url().includes('/api/gateway/v1/values-auction/start-together') &&
      request.method() === 'POST',
    { timeout: 15000 },
  )
  await dualEntry.click()
  await startTogetherRequest

  await expect(page.getByText(/你之前做过价值观拍卖|第 1 件/)).toBeVisible({ timeout: 15000 })
  expect(Array.from(hits)).toEqual(expect.arrayContaining(['POST /v1/values-auction/start-together']))
})

test('dual values auction completes from bidding to match analysis', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '使用其他手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
  await fillVerificationCode(page)
  await page.waitForURL(/\/(discover|onboarding)/, { timeout: 20000 })
  await ensureSessionProfile(page)
  const currentUserKey = await getCurrentProfileId(page)

  await page.goto(
    `http://127.0.0.1:3000/chat/demo?caseId=case-frontend-demo&counterpartId=${PARTNER_KEY}&chatTitle=测试对象`,
  )
  await expect(page.getByPlaceholder('输入消息...')).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '展开菜单' }).click()
  const dualEntry = page.getByRole('button', { name: '双人价值观拍卖' })
  await expect(dualEntry).toBeVisible()

  const startTogetherResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/gateway/v1/values-auction/start-together') &&
      response.request().method() === 'POST',
    { timeout: 15000 },
  )
  await dualEntry.click()
  const startPayload = await (await startTogetherResponse).json() as { session_id?: string }
  const sessionId = startPayload.session_id
  expect(sessionId).toBeTruthy()

  const choiceCard = page.getByText('你之前做过价值观拍卖')
  if (await choiceCard.isVisible().catch(() => false)) {
    await page.getByText('重新做一遍', { exact: true }).click()
    await page.getByRole('button', { name: '重新拍卖' }).click()
  }

  await expect(page.getByText(/第 1 件/)).toBeVisible({ timeout: 15000 })
  await assignCurrentLot(page, '2 筹码')
  await assignCurrentLot(page, '2 筹码')
  await assignCurrentLot(page, '1 筹码')
  await assignCurrentLot(page, '2 筹码')
  await assignCurrentLot(page, '1 筹码')
  await assignCurrentLot(page, '0 筹码')
  await assignCurrentLot(page, '1 筹码')
  await assignCurrentLot(page, '0 筹码')
  await assignCurrentLot(page, '1 筹码')

  await expect(page.getByRole('heading', { name: '封盘前最后调仓' })).toBeVisible({ timeout: 15000 })

  const submitResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/gateway/v1/values-auction/submit-together') &&
      response.request().method() === 'POST',
    { timeout: 15000 },
  )
  await page.getByRole('button', { name: '封盘揭晓' }).click()
  await submitResponse

  await expect(page.getByRole('heading', { name: '盲拍对照模式' })).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('你的选择', { exact: true })).toBeVisible()
  await expect(page.getByText('TA 的状态', { exact: true })).toBeVisible()

  await page.route('**/api/gateway/v1/values-auction/check-status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'both_done',
        card_type: 'values_match_analysis',
        match_data: {
          session_id: sessionId,
          schema_version: 'v2',
          alignment_score: 46,
          match_type: '需要磨合',
          user1: {
            user_key: currentUserKey,
            value_type: '稳中求进型',
            higher_order_values: {
              conservation: 0.48,
              self_enhancement: 0.305,
              self_transcendence: 0.195,
              openness_to_change: 0.02,
            },
            top3: [
              { lot_id: 'financial_freedom', title: '这辈子都不用再为钱妥协', chips: 2 },
              { lot_id: 'elite_status', title: '走到哪里都让人高看一眼', chips: 2 },
              { lot_id: 'family_health', title: '全家人健康平安到百岁', chips: 2 },
            ],
          },
          user2: {
            user_key: PARTNER_KEY,
            value_type: '理想共益型',
            higher_order_values: {
              openness_to_change: 0.34,
              self_transcendence: 0.395,
              conservation: 0.12,
              self_enhancement: 0.145,
            },
            top3: [
              { lot_id: 'total_freedom', title: '想做什么就做什么，没人管', chips: 3 },
              { lot_id: 'change_world', title: '做一件改变世界的事', chips: 3 },
              { lot_id: 'inner_peace', title: '内心平静，不再焦虑', chips: 2 },
            ],
          },
          common_lots: [],
          common_hidden_values: [],
          shared_directions: [],
          negotiable_differences: [],
          structural_tensions: [
            {
              left: 'openness_to_change',
              right: 'conservation',
              description: '你们一个更偏开放变化，一个更偏保守维持。按 Schwartz 的结构，这组价值天然存在张力，通常会落到自由度、稳定感、边界和生活节奏上。',
            },
            {
              left: 'self_enhancement',
              right: 'self_transcendence',
              description: '你们一个更偏自我提升，一个更偏超越自我。按 Schwartz 的结构，这组价值不一定不能相处，但很容易在成就追求、利他投入和资源分配上产生分歧。',
            },
          ],
          misalignments: [
            {
              type: 'value_misalign',
              lot_id: 'financial_freedom',
              description: "你看重'这辈子都不用再为钱妥协'，TA不怎么在意",
            },
            {
              type: 'value_misalign',
              lot_id: 'change_world',
              description: "TA看重'做一件改变世界的事'，你不怎么在意",
            },
          ],
          conflicts: [
            {
              type: 'structural_tension',
              description: '你们一个更偏开放变化，一个更偏保守维持。按 Schwartz 的结构，这组价值天然存在张力，通常会落到自由度、稳定感、边界和生活节奏上。',
              suggestion: '建议尽早聊清楚空间、承诺、家庭责任和现实安排。',
            },
          ],
        },
      }),
    })
  })

  await expect(page.getByRole('heading', { name: '同时揭晓仪式' })).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('你的 Top3')).toBeVisible()
  await expect(page.getByText('TA 的 Top3')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('结构性张力')).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(/一个更偏开放变化，一个更偏保守维持/).first()).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(/一个更偏自我提升，一个更偏超越自我/).first()).toBeVisible({ timeout: 15000 })
  await expect(page.getByText(/需要磨合|一般契合/)).toBeVisible({ timeout: 15000 })

  expect(Array.from(hits)).toEqual(
    expect.arrayContaining([
      'POST /v1/values-auction/start-together',
      'POST /v1/values-auction/submit-together',
      'POST /v1/values-auction/check-status',
    ]),
  )
})
