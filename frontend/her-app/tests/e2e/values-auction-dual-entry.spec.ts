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

  await expect(page.getByText(/你之前做过价值观拍卖|分配你的筹码/)).toBeVisible({ timeout: 15000 })
  expect(Array.from(hits)).toEqual(expect.arrayContaining(['POST /v1/values-auction/start-together']))
})
