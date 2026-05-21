# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/e2e/her-flow.spec.ts >> one-tap login success hits real backend
- Location: tests/e2e/her-flow.spec.ts:87:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('button', { name: '一键登录' })
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByRole('button', { name: '一键登录' })

```

```yaml
- text: H
- heading "Her" [level=1]
- paragraph: 也许在这里 你会遇见一个很特别的人
- button [disabled]
- button "微信登录" [disabled]
- button "手机号登录" [disabled]
- paragraph:
  - text: 登录即表示同意
  - button "用户协议"
  - text: 和
  - button "隐私政策"
- button
- alert
```

# Test source

```ts
  1   | import { expect, test } from '@playwright/test'
  2   | import fs from 'node:fs/promises'
  3   | 
  4   | test.setTimeout(60000)
  5   | 
  6   | const bindPhone = process.env.HER_E2E_BIND_PHONE || '13800138004'
  7   | 
  8   | async function launchToWelcome(page: import('@playwright/test').Page) {
  9   |   await page.goto('http://127.0.0.1:3000')
  10  |   await page.getByRole('button', { name: '开始遇见' }).click()
  11  |   await expect(page.getByRole('button', { name: '手机号登录' })).toBeVisible()
  12  | }
  13  | 
  14  | async function fillVerificationCode(page: import('@playwright/test').Page) {
  15  |   const code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
  16  |   const inputs = page.locator('input[inputmode="numeric"]')
  17  |   for (let i = 0; i < code.length; i += 1) {
  18  |     await inputs.nth(i).fill(code[i])
  19  |   }
  20  | }
  21  | 
  22  | function trackGatewayRequests(page: import('@playwright/test').Page) {
  23  |   const hits = new Set<string>()
  24  |   page.on('request', (request) => {
  25  |     const url = new URL(request.url())
  26  |     if (!url.pathname.startsWith('/api/gateway/')) return
  27  |     const path = url.pathname.replace('/api/gateway', '')
  28  |     hits.add(`${request.method()} ${path}`)
  29  |   })
  30  |   return hits
  31  | }
  32  | 
  33  | test('sms auth + discovery + recommendation action hit real backend', async ({ page }) => {
  34  |   const hits = trackGatewayRequests(page)
  35  | 
  36  |   await launchToWelcome(page)
  37  |   await page.getByRole('button', { name: '手机号登录' }).click()
  38  |   await page.getByPlaceholder('请输入手机号').fill('13800138000')
  39  |   await page.getByRole('button', { name: '获取验证码' }).click()
  40  |   await expect(page.getByText('输入验证码')).toBeVisible()
  41  |   await fillVerificationCode(page)
  42  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  43  | 
  44  |   await page.waitForTimeout(1500)
  45  |   const turnRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/discovery/sessions/') && request.method() === 'POST')
  46  |   await page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/).fill('我在无锡，想找认真恋爱的人')
  47  |   await page.getByRole('button', { name: '发送发现页消息' }).click()
  48  |   await turnRequest
  49  | 
  50  |   await page.getByRole('button', { name: '来信' }).click()
  51  |   await expect(page.getByText('推荐来信')).toBeVisible()
  52  |   const actionRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/recommendation/actions') && request.method() === 'POST')
  53  |   await page.locator('button[aria-label^="收藏"]').first().click()
  54  |   await actionRequest
  55  | 
  56  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  57  |     'POST /v1/auth/sms/send-code',
  58  |     'POST /v1/auth/sms/verify-code',
  59  |     'POST /v1/discovery/sessions',
  60  |     expect.stringContaining('POST /v1/discovery/sessions/'),
  61  |     'GET /v1/recommendation/cards',
  62  |   ]))
  63  |   expect(Array.from(hits).some((item) => item === 'POST /v1/recommendation/actions')).toBe(true)
  64  | })
  65  | 
  66  | test('wechat login + bind phone success hits real backend', async ({ page }) => {
  67  |   const hits = trackGatewayRequests(page)
  68  | 
  69  |   await launchToWelcome(page)
  70  |   await page.getByRole('button', { name: '微信登录' }).click()
  71  |   await expect(page.getByRole('button', { name: '绑定手机号' })).toBeVisible({ timeout: 15000 })
  72  | 
  73  |   await page.getByRole('button', { name: '绑定手机号' }).click()
  74  |   await page.getByPlaceholder('请输入手机号').fill(bindPhone)
  75  |   await page.getByRole('button', { name: '获取验证码' }).click()
  76  |   await expect(page.getByText('输入验证码')).toBeVisible()
  77  |   await fillVerificationCode(page)
  78  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  79  | 
  80  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  81  |     'POST /v1/auth/wechat/login',
  82  |     'POST /v1/auth/sms/send-code',
  83  |     'POST /v1/auth/wechat/bind-phone',
  84  |   ]))
  85  | })
  86  | 
  87  | test('one-tap login success hits real backend', async ({ page }) => {
  88  |   const hits = trackGatewayRequests(page)
  89  | 
  90  |   await launchToWelcome(page)
  91  |   await page.getByRole('button', { name: '本机号码一键登录' }).click()
> 92  |   await expect(page.getByRole('button', { name: '一键登录' })).toBeVisible({ timeout: 15000 })
      |                                                            ^ Error: expect(locator).toBeVisible() failed
  93  |   await page.getByRole('button', { name: '一键登录' }).click()
  94  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  95  | 
  96  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  97  |     'POST /v1/auth/one-tap/create',
  98  |     'POST /v1/auth/one-tap/verify',
  99  |   ]))
  100 | })
  101 | 
  102 | test('relationships and chat pages hit real backend', async ({ page }) => {
  103 |   const hits = trackGatewayRequests(page)
  104 | 
  105 |   await page.goto('http://127.0.0.1:3000')
  106 |   await page.getByRole('button', { name: '开始遇见' }).click()
  107 |   const demoToggle = page.locator('button.fixed.bottom-6.right-6')
  108 |   await demoToggle.click()
  109 |   await page.getByRole('button', { name: '关系' }).click()
  110 |   await expect(page.getByRole('heading', { name: '关系' })).toBeVisible()
  111 |   await page.getByRole('button', { name: /user-b/ }).click()
  112 |   await page.getByPlaceholder('输入消息...').fill('前端联调消息')
  113 |   await page.getByRole('button', { name: '发送消息' }).click()
  114 |   await page.waitForTimeout(1500)
  115 | 
  116 |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  117 |     'GET /v2/chat/cases/case-frontend-demo/timeline',
  118 |     expect.stringContaining('GET /v2/chat/conversations/'),
  119 |     expect.stringContaining('GET /v2/chat/conversations/'),
  120 |     expect.stringContaining('POST /v2/chat/conversations/'),
  121 |   ]))
  122 | })
  123 | 
```