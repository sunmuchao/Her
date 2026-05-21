import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(60000)

const bindPhone = process.env.HER_E2E_BIND_PHONE || '13800138004'

async function launchToWelcome(page: import('@playwright/test').Page) {
  await page.goto('http://127.0.0.1:3000')
  await page.getByRole('button', { name: '开始遇见' }).click()
  await expect(page.getByRole('button', { name: '手机号登录' })).toBeVisible()
}

async function fillVerificationCode(page: import('@playwright/test').Page) {
  const code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
  const inputs = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < code.length; i += 1) {
    await inputs.nth(i).fill(code[i])
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
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '手机号登录' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  await expect(page.getByText('输入验证码')).toBeVisible()
  await fillVerificationCode(page)
  await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })

  await page.waitForTimeout(1500)
  const turnRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/discovery/sessions/') && request.method() === 'POST')
  await page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/).fill('我在无锡，想找认真恋爱的人')
  await page.getByRole('button', { name: '发送发现页消息' }).click()
  await turnRequest

  await page.getByRole('button', { name: '来信' }).click()
  await expect(page.getByText('推荐来信')).toBeVisible()
  const actionRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/recommendation/actions') && request.method() === 'POST')
  await page.locator('button[aria-label^="收藏"]').first().click()
  await actionRequest

  expect(Array.from(hits)).toEqual(expect.arrayContaining([
    'POST /v1/auth/sms/send-code',
    'POST /v1/auth/sms/verify-code',
    'POST /v1/discovery/sessions',
    expect.stringContaining('POST /v1/discovery/sessions/'),
    'GET /v1/recommendation/cards',
  ]))
  expect(Array.from(hits).some((item) => item === 'POST /v1/recommendation/actions')).toBe(true)
})

test('wechat login + bind phone success hits real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  await page.getByRole('button', { name: '微信登录' }).click()
  await expect(page.getByRole('button', { name: '绑定手机号' })).toBeVisible({ timeout: 15000 })

  await page.getByRole('button', { name: '绑定手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill(bindPhone)
  await page.getByRole('button', { name: '获取验证码' }).click()
  await expect(page.getByText('输入验证码')).toBeVisible()
  await fillVerificationCode(page)
  await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })

  expect(Array.from(hits)).toEqual(expect.arrayContaining([
    'POST /v1/auth/wechat/login',
    'POST /v1/auth/sms/send-code',
    'POST /v1/auth/wechat/bind-phone',
  ]))
})

test('one-tap login success hits real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await launchToWelcome(page)
  const createRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/auth/one-tap/create') && request.method() === 'POST')
  await page.getByRole('button', { name: '本机号码一键登录' }).click()
  await createRequest
  await expect(page.getByRole('button', { name: '一键登录' })).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '一键登录' }).click()
  await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })

  expect(Array.from(hits)).toEqual(expect.arrayContaining([
    'POST /v1/auth/one-tap/create',
    'POST /v1/auth/one-tap/verify',
  ]))
})

test('relationships and chat pages hit real backend', async ({ page }) => {
  const hits = trackGatewayRequests(page)

  await page.goto('http://127.0.0.1:3000')
  await page.getByRole('button', { name: '开始遇见' }).click()
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
