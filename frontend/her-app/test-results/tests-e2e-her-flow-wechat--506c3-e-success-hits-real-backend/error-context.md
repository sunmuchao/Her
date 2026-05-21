# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/e2e/her-flow.spec.ts >> wechat login + bind phone success hits real backend
- Location: tests/e2e/her-flow.spec.ts:64:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('button', { name: '绑定手机号' })
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByRole('button', { name: '绑定手机号' })

```

```yaml
- main:
  - heading "小雅" [level=1]
  - paragraph: 你的专属红娘
  - button "来信 3"
  - text: 同城优先 本科以上 年龄相近 性格温柔 先跟我说说你想找什么样的人，不用一次讲完整。
  - paragraph: 刚刚
  - button "先从城市和年龄说起"
  - button "先说你最在意的 3 个条件"
  - paragraph: 为你精心挑选
  - button "林悦 林悦 28岁 上海 产品设计师 性格温和、同城、审美品味相近 95%":
    - img "林悦"
    - text: 林悦 28岁 上海 产品设计师
    - paragraph: 性格温和、同城、审美品味相近
    - text: 95%
  - button "陈思 陈思 27岁 上海 品牌策划 价值观相似、兴趣爱好匹配 92%":
    - img "陈思"
    - text: 陈思 27岁 上海 品牌策划
    - paragraph: 价值观相似、兴趣爱好匹配
    - text: 92%
  - textbox "继续告诉红娘你的要求"
  - button "发送发现页消息" [disabled]
- navigation:
  - button "3 红娘"
  - button "2 关系"
  - button "我的"
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
  6   | async function launchToWelcome(page: import('@playwright/test').Page) {
  7   |   await page.goto('http://127.0.0.1:3000')
  8   |   await page.getByRole('button', { name: '开始遇见' }).click()
  9   |   await expect(page.getByRole('button', { name: '手机号登录' })).toBeVisible()
  10  | }
  11  | 
  12  | async function fillVerificationCode(page: import('@playwright/test').Page) {
  13  |   const code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
  14  |   const inputs = page.locator('input[inputmode="numeric"]')
  15  |   for (let i = 0; i < code.length; i += 1) {
  16  |     await inputs.nth(i).fill(code[i])
  17  |   }
  18  | }
  19  | 
  20  | function trackGatewayRequests(page: import('@playwright/test').Page) {
  21  |   const hits = new Set<string>()
  22  |   page.on('request', (request) => {
  23  |     const url = new URL(request.url())
  24  |     if (!url.pathname.startsWith('/api/gateway/')) return
  25  |     const path = url.pathname.replace('/api/gateway', '')
  26  |     hits.add(`${request.method()} ${path}`)
  27  |   })
  28  |   return hits
  29  | }
  30  | 
  31  | test('sms auth + discovery + recommendation action hit real backend', async ({ page }) => {
  32  |   const hits = trackGatewayRequests(page)
  33  | 
  34  |   await launchToWelcome(page)
  35  |   await page.getByRole('button', { name: '手机号登录' }).click()
  36  |   await page.getByPlaceholder('请输入手机号').fill('13800138000')
  37  |   await page.getByRole('button', { name: '获取验证码' }).click()
  38  |   await expect(page.getByText('输入验证码')).toBeVisible()
  39  |   await fillVerificationCode(page)
  40  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  41  | 
  42  |   await page.waitForTimeout(1500)
  43  |   const turnRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/discovery/sessions/') && request.method() === 'POST')
  44  |   await page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/).fill('我在无锡，想找认真恋爱的人')
  45  |   await page.getByRole('button', { name: '发送发现页消息' }).click()
  46  |   await turnRequest
  47  | 
  48  |   await page.getByRole('button', { name: '来信' }).click()
  49  |   await expect(page.getByText('推荐来信')).toBeVisible()
  50  |   const actionRequest = page.waitForRequest((request) => request.url().includes('/api/gateway/v1/recommendation/actions') && request.method() === 'POST')
  51  |   await page.locator('button[aria-label^="收藏"]').first().click()
  52  |   await actionRequest
  53  | 
  54  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  55  |     'POST /v1/auth/sms/send-code',
  56  |     'POST /v1/auth/sms/verify-code',
  57  |     'POST /v1/discovery/sessions',
  58  |     expect.stringContaining('POST /v1/discovery/sessions/'),
  59  |     'GET /v1/recommendation/cards',
  60  |   ]))
  61  |   expect(Array.from(hits).some((item) => item === 'POST /v1/recommendation/actions')).toBe(true)
  62  | })
  63  | 
  64  | test('wechat login + bind phone success hits real backend', async ({ page }) => {
  65  |   const hits = trackGatewayRequests(page)
  66  | 
  67  |   await launchToWelcome(page)
  68  |   await page.getByRole('button', { name: '微信登录' }).click()
> 69  |   await expect(page.getByRole('button', { name: '绑定手机号' })).toBeVisible({ timeout: 15000 })
      |                                                             ^ Error: expect(locator).toBeVisible() failed
  70  | 
  71  |   await page.getByRole('button', { name: '绑定手机号' }).click()
  72  |   await page.getByPlaceholder('请输入手机号').fill('13800138003')
  73  |   await page.getByRole('button', { name: '获取验证码' }).click()
  74  |   await expect(page.getByText('输入验证码')).toBeVisible()
  75  |   await fillVerificationCode(page)
  76  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  77  | 
  78  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  79  |     'POST /v1/auth/wechat/login',
  80  |     'POST /v1/auth/sms/send-code',
  81  |     'POST /v1/auth/wechat/bind-phone',
  82  |   ]))
  83  | })
  84  | 
  85  | test('one-tap login success hits real backend', async ({ page }) => {
  86  |   const hits = trackGatewayRequests(page)
  87  | 
  88  |   await launchToWelcome(page)
  89  |   await page.getByRole('button', { name: '本机号码一键登录' }).click()
  90  |   await expect(page.getByRole('button', { name: '一键登录' })).toBeVisible({ timeout: 15000 })
  91  |   await page.getByRole('button', { name: '一键登录' }).click()
  92  |   await expect(page.getByRole('heading', { name: '小雅' })).toBeVisible({ timeout: 15000 })
  93  | 
  94  |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  95  |     'POST /v1/auth/one-tap/create',
  96  |     'POST /v1/auth/one-tap/verify',
  97  |   ]))
  98  | })
  99  | 
  100 | test('relationships and chat pages hit real backend', async ({ page }) => {
  101 |   const hits = trackGatewayRequests(page)
  102 | 
  103 |   await page.goto('http://127.0.0.1:3000')
  104 |   await page.getByRole('button', { name: '开始遇见' }).click()
  105 |   const demoToggle = page.locator('button.fixed.bottom-6.right-6')
  106 |   await demoToggle.click()
  107 |   await page.getByRole('button', { name: '关系' }).click()
  108 |   await expect(page.getByRole('heading', { name: '关系' })).toBeVisible()
  109 |   await page.getByRole('button', { name: /user-b/ }).click()
  110 |   await page.getByPlaceholder('输入消息...').fill('前端联调消息')
  111 |   await page.getByRole('button', { name: '发送消息' }).click()
  112 |   await page.waitForTimeout(1500)
  113 | 
  114 |   expect(Array.from(hits)).toEqual(expect.arrayContaining([
  115 |     'GET /v2/chat/cases/case-frontend-demo/timeline',
  116 |     expect.stringContaining('GET /v2/chat/conversations/'),
  117 |     expect.stringContaining('GET /v2/chat/conversations/'),
  118 |     expect.stringContaining('POST /v2/chat/conversations/'),
  119 |   ]))
  120 | })
  121 | 
```