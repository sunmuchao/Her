import { test, expect, Page } from '@playwright/test'

test.describe('推荐来信已读状态 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    // 登录用户
    await page.goto('/login')
    await page.fill('[name="phone"]', '13800138000')
    await page.click('button[type="submit"]')
    await page.waitForURL('/discover')
  })

  test('场景 1.1：推荐卡片点击后立即标记已读', async ({ page }) => {
    // 前置条件：用户有未读推荐卡片
    await page.goto('/discover')

    // 检查徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    expect(unreadCountBefore).toBeGreaterThan(0)

    // 打开推荐来信页
    await page.click('[data-testid="inbox-button"]')
    await page.waitForURL('/discover/inbox')

    // 检查第一个卡片有红色提醒
    const firstCard = page.locator('[data-testid="inbox-item"]').first()
    const redDotBefore = await firstCard.locator('.bg-rose').isVisible()
    expect(redDotBefore).toBe(true)

    // 点击第一个卡片
    await firstCard.click()

    // 等待进入详情页
    await page.waitForURL(/\/candidate\/\d+/)

    // 返回推荐来信页
    await page.click('[data-testid="back-button"]')
    await page.waitForURL('/discover/inbox')

    // 验证红色提醒消失
    const redDotAfter = await firstCard.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(false)

    // 验证徽章数字减少
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 1)
  })

  test('场景 1.2：多个未读卡片顺序点击', async ({ page }) => {
    await page.goto('/discover')

    // 检查初始徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    expect(unreadCountBefore).toBeGreaterThan(2)

    // 打开推荐来信页
    await page.click('[data-testid="inbox-button"]')

    // 依次点击 3 个卡片
    for (let i = 0; i < 3; i++) {
      const card = page.locator('[data-testid="inbox-item"]').nth(i)
      await card.click()
      await page.waitForURL(/\/candidate\/\d+/)
      await page.click('[data-testid="back-button"]')
      await page.waitForURL('/discover/inbox')
    }

    // 验证徽章数字减少 3
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 3)
  })

  test('场景 1.3：被动推荐点击后不立即标记已读', async ({ page }) => {
    await page.goto('/discover/inbox')

    // 过滤被动推荐（有人想认识你）
    await page.click('[data-testid="filter-interest"]')

    // 检查徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 点击第一个被动推荐卡片
    const firstInterestCard = page.locator('[data-testid="inbox-item"]').first()
    await firstInterestCard.click()

    // 等待进入详情页
    await page.waitForURL(/\/candidate\/\d+/)

    // 返回推荐来信页（不点击"愿意认识"）
    await page.click('[data-testid="back-button"]')

    // 验证徽章数字不减少
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore)
  })

  test('场景 1.4：被动推荐回复后标记已读', async ({ page }) => {
    await page.goto('/discover/inbox')

    // 过滤被动推荐
    await page.click('[data-testid="filter-interest"]')

    // 检查徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 点击第一个被动推荐卡片
    const firstInterestCard = page.locator('[data-testid="inbox-item"]').first()
    await firstInterestCard.click()

    // 等待进入详情页
    await page.waitForURL(/\/candidate\/\d+/)

    // 点击"愿意认识"
    await page.click('[data-testid="accept-button"]')

    // 等待回复成功
    await page.waitForSelector('[data-testid="submitted-hint"]')

    // 返回推荐来信页
    await page.click('[data-testid="back-button"]')

    // 验证徽章数字减少
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 1)
  })

  test('场景 2.1：API 失败处理', async ({ page }) => {
    // Mock API 失败
    await page.route('/api/v1/recommendation/cards/read', (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal Server Error' }),
      })
    })

    await page.goto('/discover/inbox')

    // 点击第一个卡片
    const firstCard = page.locator('[data-testid="inbox-item"]').first()
    await firstCard.click()

    // 等待进入详情页
    await page.waitForURL(/\/candidate\/\d+/)

    // 返回推荐来信页
    await page.click('[data-testid="back-button"]')

    // 验证红色提醒不消失
    const redDotAfter = await firstCard.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(true)

    // 验证徽章数字不减少
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    expect(parseInt(badgeAfter || '0')).toBeGreaterThan(0)
  })

  test('场景 3.1：并发点击多个卡片', async ({ page }) => {
    await page.goto('/discover/inbox')

    // 检查初始徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    expect(unreadCountBefore).toBeGreaterThan(2)

    // 快速点击 3 个卡片（不等待返回）
    const cards = page.locator('[data-testid="inbox-item"]')
    const promises = []
    for (let i = 0; i < 3; i++) {
      promises.push(
        cards.nth(i).click()
      )
    }

    // 并发点击
    await Promise.all(promises)

    // 等待最后一个详情页加载
    await page.waitForURL(/\/candidate\/\d+/)

    // 返回推荐来信页
    await page.click('[data-testid="back-button"]')

    // 验证徽章数字减少 3
    await page.goto('/discover')
    const badgeAfter = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 3)
  })

  test('场景 4.1：网络延迟场景', async ({ page }) => {
    // Mock API 响应延迟 3 秒
    await page.route('/api/v1/recommendation/cards/read', (route) => {
      setTimeout(() => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({}),
        })
      }, 3000)
    })

    await page.goto('/discover/inbox')

    // 点击第一个卡片
    const firstCard = page.locator('[data-testid="inbox-item"]').first()
    await firstCard.click()

    // 验证立即进入详情页（不等待 API）
    await page.waitForURL(/\/candidate\/\d+/, { timeout: 500 })

    // 返回推荐来信页
    await page.click('[data-testid="back-button"]')

    // 等待 API 完成（红色提醒消失）
    await page.waitForTimeout(3500)

    // 验证红色提醒消失
    const redDotAfter = await firstCard.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(false)
  })

  test('场景 5.1：混合场景测试', async ({ page }) => {
    await page.goto('/discover')

    // 检查初始徽章数字
    const badgeBefore = await page.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 步骤 1：点击推荐卡片 A
    await page.click('[data-testid="inbox-button"]')
    await page.locator('[data-testid="inbox-item"]').first().click()
    await page.waitForURL(/\/candidate\/\d+/)
    await page.click('[data-testid="back-button"]')

    // 验证数字减少 1
    await page.goto('/discover')
    const badge1 = await page.locator('[data-testid="inbox-badge"]').textContent()
    expect(parseInt(badge1 || '0')).toBe(unreadCountBefore - 1)

    // 步骤 2：点击被动推荐 B（不回复）
    await page.goto('/discover/inbox')
    await page.click('[data-testid="filter-interest"]')
    await page.locator('[data-testid="inbox-item"]').first().click()
    await page.waitForURL(/\/candidate\/\d+/)
    await page.click('[data-testid="back-button"]')

    // 验证数字不减少
    await page.goto('/discover')
    const badge2 = await page.locator('[data-testid="inbox-badge"]').textContent()
    expect(parseInt(badge2 || '0')).toBe(unreadCountBefore - 1)

    // 步骤 3：点击推荐卡片 C
    await page.goto('/discover/inbox')
    await page.click('[data-testid="filter-all"]')
    await page.locator('[data-testid="inbox-item"]').nth(1).click()
    await page.waitForURL(/\/candidate\/\d+/)
    await page.click('[data-testid="back-button"]')

    // 验证数字减少 1
    await page.goto('/discover')
    const badge3 = await page.locator('[data-testid="inbox-badge"]').textContent()
    expect(parseInt(badge3 || '0')).toBe(unreadCountBefore - 2)

    // 步骤 4：点击被动推荐 B，回复
    await page.goto('/discover/inbox')
    await page.click('[data-testid="filter-interest"]')
    await page.locator('[data-testid="inbox-item"]').first().click()
    await page.waitForURL(/\/candidate\/\d+/)
    await page.click('[data-testid="accept-button"]')
    await page.waitForSelector('[data-testid="submitted-hint"]')
    await page.click('[data-testid="back-button"]')

    // 验证数字减少 1
    await page.goto('/discover')
    const badge4 = await page.locator('[data-testid="inbox-badge"]').textContent()
    expect(parseInt(badge4 || '0')).toBe(unreadCountBefore - 3)
  })

  test('场景 6.1：跨页面同步', async ({ page }) => {
    // 打开两个标签页
    const page1 = page
    const page2 = await page.context().newPage()

    // 标签页 A：点击推荐卡片
    await page1.goto('/discover/inbox')
    await page1.locator('[data-testid="inbox-item"]').first().click()
    await page1.waitForURL(/\/candidate\/\d+/)
    await page1.click('[data-testid="back-button"]')

    // 标签页 A 徽章更新
    await page1.goto('/discover')
    const badge1 = await page1.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCount1 = parseInt(badge1 || '0')

    // 标签页 B 徽章不自动更新（依赖 window focus）
    await page2.goto('/discover')
    const badge2Before = await page2.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCount2Before = parseInt(badge2Before || '0')

    // 切换标签页 B 到前台（触发 window focus）
    await page2.bringToFront()
    await page2.waitForTimeout(500)

    // 标签页 B 徽章更新
    const badge2After = await page2.locator('[data-testid="inbox-badge"]').textContent()
    const unreadCount2After = parseInt(badge2After || '0')

    expect(unreadCount2After).toBe(unreadCount2Before - 1)

    // 关闭标签页 B
    await page2.close()
  })

  test('场景 7.1：页面刷新后状态一致', async ({ page }) => {
    await page.goto('/discover/inbox')

    // 点击第一个卡片
    const firstCard = page.locator('[data-testid="inbox-item"]').first()
    await firstCard.click()
    await page.waitForURL(/\/candidate\/\d+/)
    await page.click('[data-testid="back-button"]')

    // 刷新页面
    await page.reload()

    // 验证红色提醒消失（依赖后端状态）
    const redDotAfter = await firstCard.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(false)
  })
})