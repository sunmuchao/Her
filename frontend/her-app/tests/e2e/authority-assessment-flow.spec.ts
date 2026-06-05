import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(180000)

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
          name: '测评E2E用户',
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

async function loginToDiscover(page: import('@playwright/test').Page) {
  await launchToWelcome(page)
  await expect(page.getByRole('button', { name: '使用其他手机号' })).toBeVisible()
  await page.getByRole('button', { name: '使用其他手机号' }).click()
  await page.getByPlaceholder('请输入手机号').fill('13800138000')
  await page.getByRole('button', { name: '获取验证码' }).click()
  await fillVerificationCode(page)
  await page.waitForURL(/\/discover/, { timeout: 30000 })
  await ensureSessionProfile(page)
  await page.goto('http://127.0.0.1:3000/discover')
  await expect(page.getByText('小雅')).toBeVisible({ timeout: 15000 })
}

async function openAssessment(page: import('@playwright/test').Page, menuLabel: string, introTitle: string) {
  await page.getByRole('button', { name: '展开菜单' }).click()
  await page.getByRole('button', { name: '心理测评' }).click()
  await page.getByRole('button', { name: menuLabel }).click()
  await expect(page.getByRole('heading', { name: introTitle })).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('button', { name: '开始探索' })).toBeVisible()
}

async function completeCurrentAssessment(
  page: import('@playwright/test').Page,
  answerIndex: number,
  resultText: string,
) {
  await page.getByRole('button', { name: '开始探索' }).click()

  for (let step = 0; step < 200; step += 1) {
    const result = page.getByText(resultText, { exact: true })
    if (await result.isVisible().catch(() => false)) {
      return
    }

    const continueButton = page.getByRole('button', { name: '继续探索下一维度' })
    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click()
      continue
    }

    const options = page.locator('[role="option"]:not([disabled])')
    const optionCount = await options.count()
    if (optionCount > 0) {
      const targetIndex = Math.min(answerIndex, optionCount - 1)
      await options.nth(targetIndex).click()
      await page.waitForTimeout(700)
      continue
    }

    await page.waitForTimeout(300)
  }

  throw new Error(`Assessment did not reach result card: ${resultText}`)
}

test('big five and sternberg flows render MBTI-like cards while keeping result explanation in Xiaoya', async ({ page }) => {
  await loginToDiscover(page)

  await openAssessment(page, '大五人格测评', '大五人格特质')
  await completeCurrentAssessment(page, 4, 'BIG FIVE')
  await expect(page.getByText('大五本质上是连续维度，这里的标签是对高低分组合的人话摘要。')).toBeVisible()
  await expect(page.getByText('核心解释')).toHaveCount(0)
  await expect(page.getByText('重点是').first()).toBeVisible({ timeout: 20000 })
  await expect(page.getByText('如果你愿意，我下一条还能继续陪你拆')).toBeVisible({ timeout: 20000 })

  await openAssessment(page, '爱情三元论测评', '爱情三元论测评')
  await completeCurrentAssessment(page, 8, '三元结构')
  await expect(page.getByText('以下标签直接对应三元论的三条分数高低，是结构摘要，不是原理论里的固定爱情类型判定。')).toBeVisible()
  await expect(page.getByText('核心解释')).toHaveCount(0)
  await expect(page.getByText('三元论看的不是给你判成哪一种固定爱情类型')).toBeVisible({ timeout: 20000 })
  await expect(page.getByText('重点是').first()).toBeVisible({ timeout: 20000 })
})
