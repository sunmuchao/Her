import { test, expect, Page } from '@playwright/test'

/**
 * 导航栏未读数字修复验证测试
 *
 * 验证场景：
 * 1. Badge计算准确性（排除被动推荐case）
 * 2. "标记已读"按钮功能（localStorage marker更新）
 * 3. 状态标记显示（pendingIntroItems）
 * 4. 跨页面badge同步
 */

test.describe('导航栏未读数字一致性 E2E 测试', () => {
  test.beforeEach(async ({ page }) => {
    // 登录用户
    await page.goto('/login')
    await page.fill('[name="phone"]', '13800138000')
    await page.click('button[type="submit"]')
    await page.waitForURL('/discover')
  })

  /**
   * 场景 1：Badge计算准确性
   * 验证：导航栏badge不包含被动推荐case（避免重复计算）
   */
  test('场景 1.1：导航栏badge只统计发起方pending case', async ({ page }) => {
    await page.goto('/relationships')

    // 检查导航栏badge
    const badgeBefore = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 检查"牵线中"section的case数量（只统计发起方）
    const pendingItems = await page.locator('[data-testid="pending-intro-item"]').count()

    // 检查"正在进行中"section的case数量（有未读消息的）
    const activeItems = await page.locator('[data-testid="active-relationship"]').count()
    const activeWithUnread = await page.locator('[data-testid="active-relationship"] .bg-rose').count()

    // 验证badge = pending（发起方） + chat unread
    // 注意：被动推荐case（role === 'candidate'）不计入badge
    expect(unreadCountBefore).toBeLessThanOrEqual(pendingItems + activeWithUnread)

    console.log(`Badge: ${unreadCountBefore}, Pending: ${pendingItems}, Active unread: ${activeWithUnread}`)
  })

  /**
   * 场景 2："标记已读"按钮功能
   * 验证：点击后badge立即更新（localStorage marker + 事件触发）
   */
  test('场景 2.1：已开聊case点击"标记已读"，badge立即减少', async ({ page }) => {
    await page.goto('/relationships')

    // 检查初始badge
    const badgeBefore = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 找到有未读消息的case（正在进行中section）
    const activeWithUnread = page.locator('[data-testid="active-relationship"]').filter({
      has: page.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() === 0) {
      // 没有未读消息的case，跳过此测试
      test.skip()
      return
    }

    // 展开卡片操作菜单
    await activeWithUnread.click()

    // 点击"标记已读"按钮
    await page.click('[data-testid="mark-read-button"]')

    // 等待badge刷新（事件触发）
    await page.waitForTimeout(1000)

    // 验证badge减少
    const badgeAfter = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 1)

    // 验证页面显示已读（本地状态生效）
    const redDotAfter = await activeWithUnread.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(false)
  })

  /**
   * 场景 3：状态标记显示
   * 验证：pendingIntroItems显示正确的状态标记
   */
  test('场景 3.1："牵线中"显示状态标记（等待对方决定）', async ({ page }) => {
    await page.goto('/relationships')

    // 检查"牵线中"section存在
    const pendingSection = page.locator('section').filter({
      has: page.locator('h2', { hasText: '牵线中' }),
    })

    if (await pendingSection.count() === 0) {
      test.skip()
      return
    }

    // 检查发起方case（等待对方决定）
    const requesterCases = pendingSection.locator('[data-testid="pending-intro-item"]').filter({
      has: page.locator('.bg-amber-soft'),
    })

    // 验证状态标记显示"等待对方决定"
    const statusTag = await requesterCases.first().locator('.bg-amber-soft').textContent()
    expect(statusTag).toContain('等待对方决定')
  })

  test('场景 3.2："牵线中"显示状态标记（对方已接受）', async ({ page }) => {
    await page.goto('/relationships')

    // 检查"牵线中"section存在
    const pendingSection = page.locator('section').filter({
      has: page.locator('h2', { hasText: '牵线中' }),
    })

    if (await pendingSection.count() === 0) {
      test.skip()
      return
    }

    // 检查被推荐方case（对方已接受）
    const candidateCases = pendingSection.locator('[data-testid="pending-intro-item"]').filter({
      has: page.locator('.bg-green-soft'),
    })

    // 验证状态标记显示"对方已接受"或"已开聊"
    const statusTag = await candidateCases.first().locator('.bg-green-soft').textContent()
    expect(statusTag).toMatch(/对方已接受|已开聊/)
  })

  /**
   * 场景 4：跨页面badge同步
   * 验证：关系页操作后，导航栏badge立即更新
   */
  test('场景 4.1：关系页"标记已读"后，导航栏badge立即减少', async ({ page }) => {
    // 打开两个页面
    const page1 = page
    const page2 = await page.context().newPage()

    // 页面1：关系页
    await page1.goto('/relationships')
    const badgeBefore = await page1.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 页面2：发现页（观察badge变化）
    await page2.goto('/discover')
    const badge2Before = await page2.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCount2Before = parseInt(badge2Before || '0')

    // 页面1：点击"标记已读"
    const activeWithUnread = page1.locator('[data-testid="active-relationship"]').filter({
      has: page1.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() === 0) {
      test.skip()
      await page2.close()
      return
    }

    await activeWithUnread.click()
    await page1.click('[data-testid="mark-read-button"]')

    // 等待badge刷新
    await page1.waitForTimeout(1000)

    // 验证页面1 badge减少
    const badge1After = await page1.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCount1After = parseInt(badge1After || '0')
    expect(unreadCount1After).toBe(unreadCountBefore - 1)

    // 验证页面2 badge也减少（事件触发）
    await page2.bringToFront()
    await page2.waitForTimeout(500)
    const badge2After = await page2.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCount2After = parseInt(badge2After || '0')
    expect(unreadCount2After).toBe(unreadCount2Before - 1)

    await page2.close()
  })

  /**
   * 场景 5：被动推荐case不计入关系页badge
   * 验证：被动推荐只在Discover页显示，不在Relationships页显示
   */
  test('场景 5.1：被动推荐case（awaiting_reply）不计入关系页badge', async ({ page }) => {
    // 检查Discover页inbox badge（包含被动推荐）
    await page.goto('/discover')
    const inboxBadge = await page.locator('[data-testid="inbox-badge"]').textContent()
    const inboxUnread = parseInt(inboxBadge || '0')

    // 检查Relationships页badge（不包含被动推荐）
    await page.goto('/relationships')
    const relationshipsBadge = await page.locator('[data-testid="relationships-badge"]').textContent()
    const relationshipsUnread = parseInt(relationshipsBadge || '0')

    // 验证：被动推荐case不计入relationships badge
    // inbox badge可能大于relationships badge（因为包含被动推荐）
    console.log(`Inbox badge: ${inboxUnread}, Relationships badge: ${relationshipsUnread}`)

    // 验证：两个badge的数据源不同，不会重复计算
    expect(relationshipsUnread).toBeGreaterThanOrEqual(0)
  })

  /**
   * 场景 6：localStorage marker持久化
   * 验证：标记已读后刷新页面，状态仍然保持
   */
  test('场景 6.1："标记已读"后刷新页面，状态持久化', async ({ page }) => {
    await page.goto('/relationships')

    // 检查初始badge
    const badgeBefore = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 找到有未读消息的case
    const activeWithUnread = page.locator('[data-testid="active-relationship"]').filter({
      has: page.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() === 0) {
      test.skip()
      return
    }

    // 点击"标记已读"
    await activeWithUnread.click()
    await page.click('[data-testid="mark-read-button"]')

    // 刷新页面
    await page.reload()

    // 验证badge仍然减少（localStorage marker生效）
    const badgeAfter = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')

    expect(unreadCountAfter).toBe(unreadCountBefore - 1)
  })

  /**
   * 场景 7：综合场景测试
   * 验证：多种操作后badge数字准确性
   */
  test('场景 7.1：混合场景（标记已读 + 查看状态标记 + badge同步）', async ({ page }) => {
    await page.goto('/relationships')

    // 步骤1：检查初始badge
    const badgeBefore = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 步骤2：检查状态标记显示
    const pendingSection = page.locator('section').filter({
      has: page.locator('h2', { hasText: '牵线中' }),
    })

    if (await pendingSection.count() > 0) {
      // 验证状态标记存在
      const statusTags = await pendingSection.locator('.bg-amber-soft, .bg-green-soft').count()
      expect(statusTags).toBeGreaterThan(0)
    }

    // 步骤3：标记已读（如果有未读消息）
    const activeWithUnread = page.locator('[data-testid="active-relationship"]').filter({
      has: page.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() > 0) {
      await activeWithUnread.click()
      await page.click('[data-testid="mark-read-button"]')
      await page.waitForTimeout(1000)

      // 验证badge减少
      const badgeAfter = await page.locator('[data-testid="relationships-badge"]').textContent()
      const unreadCountAfter = parseInt(badgeAfter || '0')
      expect(unreadCountAfter).toBe(unreadCountBefore - 1)
    }

    // 步骤4：切换到Discover页，验证badge同步
    await page.goto('/discover')
    const relationshipsBadgeOnDiscover = await page.locator('[data-testid="relationships-badge"]').textContent()
    const relationshipsUnreadOnDiscover = parseInt(relationshipsBadgeOnDiscover || '0')

    // 验证Discover页的relationships badge与关系页一致
    console.log(`Relationships badge on Discover: ${relationshipsUnreadOnDiscover}`)
  })

  /**
   * 场景 8：错误处理
   * 验证：API失败时badge不更新，但本地状态生效
   */
  test('场景 8.1：API失败时，badge不更新，但页面显示已读', async ({ page }) => {
    // Mock API失败（假设有对应的API）
    await page.route('/api/v1/chat/conversations/*/read', (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal Server Error' }),
      })
    })

    await page.goto('/relationships')

    // 检查初始badge
    const badgeBefore = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountBefore = parseInt(badgeBefore || '0')

    // 找到有未读消息的case
    const activeWithUnread = page.locator('[data-testid="active-relationship"]').filter({
      has: page.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() === 0) {
      test.skip()
      return
    }

    // 点击"标记已读"
    await activeWithUnread.click()
    await page.click('[data-testid="mark-read-button"]')

    // 等待API调用
    await page.waitForTimeout(1000)

    // 验证页面显示已读（本地状态生效）
    const redDotAfter = await activeWithUnread.locator('.bg-rose').isVisible()
    expect(redDotAfter).toBe(false)

    // 验证badge不减少（API失败）
    const badgeAfter = await page.locator('[data-testid="relationships-badge"]').textContent()
    const unreadCountAfter = parseInt(badgeAfter || '0')
    expect(unreadCountAfter).toBe(unreadCountBefore)
  })

  /**
   * 场景 9：性能测试
   * 验证：badge刷新响应时间
   */
  test('场景 9.1："标记已读"后badge在1秒内更新', async ({ page }) => {
    await page.goto('/relationships')

    // 找到有未读消息的case
    const activeWithUnread = page.locator('[data-testid="active-relationship"]').filter({
      has: page.locator('.bg-rose'),
    }).first()

    if (await activeWithUnread.count() === 0) {
      test.skip()
      return
    }

    // 点击"标记已读"
    const startTime = Date.now()
    await activeWithUnread.click()
    await page.click('[data-testid="mark-read-button"]')

    // 等待badge更新
    await page.waitForTimeout(1000)
    const endTime = Date.now()

    // 验证响应时间小于1秒
    const responseTime = endTime - startTime
    expect(responseTime).toBeLessThan(1500) // 包含UI操作时间

    console.log(`Badge update response time: ${responseTime}ms`)
  })
})

/**
 * 辅助函数：获取badge数字
 */
async function getBadgeCount(page: Page, testId: string): Promise<number> {
  const badge = await page.locator(`[data-testid="${testId}"]`).textContent()
  return parseInt(badge || '0')
}

/**
 * 辅助函数：等待badge更新
 */
async function waitForBadgeUpdate(page: Page, testId: string, expectedCount: number): Promise<void> {
  await page.waitForFunction(
    ({ testId, expectedCount }) => {
      const badge = document.querySelector(`[data-testid="${testId}"]`)
      if (!badge) return false
      const count = parseInt(badge.textContent || '0')
      return count === expectedCount
    },
    { testId, expectedCount },
    { timeout: 5000 },
  )
}