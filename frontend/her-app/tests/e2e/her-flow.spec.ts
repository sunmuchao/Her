import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

const seenRequests = new Set<string>()

test.setTimeout(120000)

async function fillVerificationCode(page: import('@playwright/test').Page, code: string) {
  const digits = code.slice(0, 6).split('')
  const inputs = page.locator('input[inputmode="numeric"]')
  for (let i = 0; i < digits.length; i += 1) {
    await inputs.nth(i).fill(digits[i])
  }
}

test('real backend wiring smoke test', async ({ page }) => {
  const hitUrls: string[] = []
  page.on('request', (request) => {
    const url = request.url()
    if (url.includes('/api/gateway/')) {
      hitUrls.push(`${request.method()} ${url}`)
      seenRequests.add(`${request.method()} ${new URL(url).pathname.replace('/api/gateway', '')}`)
    }
  })

  await page.goto('http://127.0.0.1:3000')
  await expect(page.getByRole('button', { name: '开始遇见' })).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '开始遇见' }).click()

  await page.getByRole('button', { name: '手机号登录' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()

  await expect(page.getByText('输入验证码')).toBeVisible()
  const smsCode = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim()
  await fillVerificationCode(page, smsCode)
  await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })

  await page.getByPlaceholder(/继续告诉红娘|输入你的想法/).fill('我在无锡，想找认真恋爱的人')
  await page.getByRole('button', { name: '发送发现页消息' }).click()
  await page.waitForTimeout(1500)

  await page.getByRole('button', { name: '来信' }).click()
  await expect(page.getByText('推荐来信')).toBeVisible()
  await page.locator('button[aria-label^="收藏"]').first().click()
  await page.locator('header button').first().click()

  await page.getByRole('button', { name: '关系' }).click()
  await expect(page.getByRole('heading', { name: '关系' })).toBeVisible()
  await page.getByText(/主群|私聊|红娘/).first().click()
  await page.getByPlaceholder(/说点什么|输入/).fill('前端联调消息')
  await page.getByRole('button', { name: '发送消息' }).click()

  await page.locator('button').nth(0).click()
  await page.getByRole('button', { name: '我的' }).click()
  await expect(page.getByText(/我的|认证/)).toBeVisible()

  const demoToggle = page.locator('button.fixed.bottom-6.right-6')
  await demoToggle.click()
  await page.getByRole('button', { name: '欢迎页' }).click()
  await expect(page.getByRole('button', { name: '微信登录' })).toBeVisible()

  await page.getByRole('button', { name: '微信登录' }).click()
  await expect(page.getByText('欢迎，测试微信用户')).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: '绑定手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  const bindCode = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim()
  await fillVerificationCode(page, bindCode)
  await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })

  await demoToggle.click()
  await page.getByRole('button', { name: '欢迎页' }).click()
  await page.getByRole('button', { name: '本机号码一键登录' }).click()
  await expect(page.getByText(/一键登录未配置|auth_one_tap_attempts/)).toBeVisible({ timeout: 15000 })

  console.log('Gateway hits:')
  for (const item of hitUrls) {
    console.log(item)
  }

  expect(Array.from(seenRequests)).toEqual(expect.arrayContaining([
    'POST /v1/auth/sms/send-code',
    'POST /v1/auth/sms/verify-code',
    'POST /v1/discovery/sessions',
    expect.stringContaining('POST /v1/discovery/sessions/'),
    'GET /v1/recommendation/cards',
    'POST /v1/recommendation/actions',
    'GET /v2/chat/cases/case-frontend-demo/timeline',
    expect.stringContaining('GET /v2/chat/conversations/'),
    expect.stringContaining('POST /v2/chat/conversations/'),
    'POST /v1/auth/wechat/login',
    'POST /v1/auth/wechat/bind-phone',
    'POST /v1/auth/one-tap/create',
  ]))
})
