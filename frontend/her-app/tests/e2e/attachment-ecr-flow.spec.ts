import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'

test.setTimeout(300000)

async function launchToWelcome(page: import('@playwright/test').Page) {
  await page.context().clearCookies()
  await page.goto('http://127.0.0.1:3000/splash')
  await page.evaluate(() => {
    window.localStorage.clear()
  })
  await page.reload()
  await page.getByRole('button', { name: '开始了解' }).click()
  await expect(page).toHaveURL(/\/welcome/)
}

async function fillVerificationCode(page: import('@playwright/test').Page) {
  let code = ''
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      code = (await fs.readFile('/tmp/her_sms_code.txt', 'utf8')).trim().slice(0, 6)
      if (code.length === 6) break
    } catch {
      // wait for gateway shell stub
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
    throw new Error('E2E: could not link requester/profile for attachment assessment')
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

async function openAttachmentAssessment(page: import('@playwright/test').Page) {
  await page.goto('http://127.0.0.1:3000/discover')
  await expect(page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/)).toBeVisible({ timeout: 20000 })

  await page.getByRole('button', { name: '展开菜单' }).click()
  await page.getByRole('button', { name: '心理测评' }).click()
  await page.getByRole('button', { name: /依恋风格测评|依恋风格|相处模式/ }).first().click()
  await expect(page.getByRole('button', { name: /开始探索|继续测评/ })).toBeVisible({ timeout: 15000 })
  await page.getByRole('button', { name: /开始探索|继续测评/ }).click()
}

async function runScenario(
  page: import('@playwright/test').Page,
  answers: string[],
  expectedType: string,
) {
  const questionTexts: string[] = []

  for (let i = 0; i < answers.length; i += 1) {
    await expect(page.locator('[role="listbox"][aria-label="选择答案"]')).toBeVisible({ timeout: 15000 })
    const optionButtons = page.locator('[role="listbox"][aria-label="选择答案"] button[aria-label^="选项 "]')
    const optionCount = await optionButtons.count()
    expect(optionCount).toBe(5)

    const questionText = await page.locator('text=/你|对方|关系/').first().textContent()
    questionTexts.push(questionText || '')

    await page.locator(`button[aria-label^="选项 ${answers[i]}:"]`).first().click()
    if (i === 5) {
      await expect(page.getByText('关系不安度')).toBeVisible({ timeout: 15000 })
      await page.getByRole('button', { name: /继续|继续测评|下一个/ }).click()
    }
  }

  await expect(page.getByText('ECR 坐标')).toBeVisible({ timeout: 20000 })
  await expect(page.locator('span').filter({ hasText: expectedType }).first()).toBeVisible({ timeout: 15000 })
  await expect(page.getByText('你的关系驱动力')).toBeVisible()
  await expect(page.getByText('最容易触发你的时刻')).toBeVisible()
  await expect(page.getByText('什么会让你重新稳定下来')).toBeVisible()
  await expect(page.getByText('更适合你的沟通方式')).toBeVisible()

  const bodyText = await page.locator('#main-content').innerText()

  return {
    questionTexts,
    bodyText: bodyText || '',
  }
}

async function readCurrentDiscoverySessionId(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const ctx = JSON.parse(window.localStorage.getItem('her_session_context') || '{}')
    const profileId = ctx.profileId
    if (!profileId) return null
    return window.localStorage.getItem(`her.discovery.session.${profileId}`)
  })
}

test('attachment assessment follows ECR two-axis model in frontend', async ({ page }) => {
  const scenarios = [
    {
      phone: '13800138010',
      expectedType: '稳定靠近型',
      answers: Array(12).fill('A'),
      expectedSignals: ['低不安、低后撤', '反复设防'],
    },
    {
      phone: '13800138011',
      expectedType: '高敏确认型',
      answers: [...Array(6).fill('E'), ...Array(6).fill('A')],
      expectedSignals: ['高不安、低后撤', '在意关系有没有持续回应'],
    },
    {
      phone: '13800138012',
      expectedType: '边界后撤型',
      answers: [...Array(6).fill('A'), ...Array(6).fill('E')],
      expectedSignals: ['低不安、高后撤', '空间和自主感'],
    },
    {
      phone: '13800138013',
      expectedType: '拉扯矛盾型',
      answers: Array(12).fill('E'),
      expectedSignals: ['高不安、高后撤', '想靠近和想后退'],
    },
  ]

  for (const scenario of scenarios) {
    await launchToWelcome(page)
    await page.getByRole('button', { name: '使用其他手机号' }).click()
    await page.getByPlaceholder('请输入手机号').fill(scenario.phone)
    await page.getByRole('button', { name: '获取验证码' }).click()
    await expect(page).toHaveURL(/\/login\/verify/, { timeout: 15000 })
    await fillVerificationCode(page)
    await page.waitForURL(/\/(discover|onboarding)/, { timeout: 20000 })
    await ensureSessionProfile(page)
    await openAttachmentAssessment(page)

    const result = await runScenario(page, scenario.answers, scenario.expectedType)

    // All questions should be relationship/anxiety/avoidance oriented instead of old four-type wording.
    expect(result.questionTexts.some((text) => text.includes('稳如老狗'))).toBeFalsy()
    expect(result.questionTexts.some((text) => text.includes('赛博怨妇'))).toBeFalsy()

    // Result should expose the two ECR axes in UI.
    expect(result.bodyText).toContain('关系不安度')
    expect(result.bodyText).toContain('亲密后撤度')
    expect(result.bodyText).toContain('ECR 坐标')

    for (const signal of scenario.expectedSignals) {
      expect(result.bodyText).toContain(signal)
    }

    // Frontend should ideally surface Xiaoya follow-up after result. If this fails, the integration is broken.
    expect(result.bodyText).toContain('你的关系驱动力')

    const sessionId = await readCurrentDiscoverySessionId(page)
    expect(sessionId).toBeTruthy()

    await page.waitForTimeout(3000)
    await page.goto(`http://127.0.0.1:3000/discover?session=${sessionId}`)
    await expect(page.getByPlaceholder(/继续告诉红娘你的要求|输入你的想法/)).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('ECR 坐标')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('#main-content')).toContainText('关系不安度')
    await expect(page.getByText('亲爱的，这次我按依恋研究里更常用的两条轴，帮你翻译成好懂的话。')).toBeVisible({
      timeout: 15000,
    })
  }
})
