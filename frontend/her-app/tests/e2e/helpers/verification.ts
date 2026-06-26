/**
 * 视频验证流程 E2E 测试辅助函数
 */

/**
 * 模拟用户登录
 */
export async function loginAsUser(
  page: any,
  userId: string,
  options?: { profileId?: number }
) {
  await page.goto('/splash')
  await page.evaluate((opts: { userId: string; profileId?: number }) => {
    const ctx = {
      accessToken: 'test-token',
      userId: opts.userId,
      profileId: opts.profileId || 123,
      profileLinked: true,
    }
    window.localStorage.setItem('her_session_context', JSON.stringify(ctx))
  }, { userId, ...options })
}

/**
 * 创建验证挑战
 */
export async function createChallenge(page: any) {
  const btn = page.getByRole('button', { name: '开始验证' })
  await btn.click()
  await page.waitForRequest((req: any) =>
    req.url().includes('/v1/verifications/live-video-challenges')
  )
}

/**
 * 提交验证视频
 */
export async function submitVerification(page: any) {
  // 模拟视频数据
  await page.evaluate(() => {
    window.localStorage.setItem('test_video_base64', 'STUB_VIDEO_BASE64')
  })

  const btn = page.getByRole('button', { name: '提交验证' })
  await btn.click()
}

/**
 * 获取提交验证请求
 */
export async function getSubmitRequest(page: any) {
  return page.waitForRequest(
    (req: any) =>
      req.url().includes('/v1/verifications/live-video-submissions') &&
      req.method() === 'POST'
  )
}

/**
 * 模拟 session 变化
 */
export async function changeSessionProfileId(page: any, newProfileId: number) {
  await page.evaluate((profileId: number) => {
    const ctx = JSON.parse(
      window.localStorage.getItem('her_session_context') || '{}'
    )
    ctx.profileId = profileId
    window.localStorage.setItem('her_session_context', JSON.stringify(ctx))
  }, newProfileId)
}

/**
 * 模拟状态过期
 */
export async function expireVerificationState(page: any) {
  await page.evaluate(() => {
    const state = JSON.parse(
      window.localStorage.getItem('her_verification_flow_state') || '{}'
    )
    state.createdAt = Date.now() - 16 * 60 * 1000 // 16分钟前
    window.localStorage.setItem('her_verification_flow_state', JSON.stringify(state))
  })
}

/**
 * 模拟提交失败
 */
export async function mockSubmitFailure(page: any, errorMessage: string) {
  await page.route('**/v1/verifications/live-video-submissions', (route: any) => {
    route.fulfill({
      status: 400,
      body: JSON.stringify({ error: { message: errorMessage } }),
    })
  })
}

/**
 * 验证锁定状态是否清理
 */
export async function isVerificationStateCleared(page: any): Promise<boolean> {
  return await page.evaluate(() => {
    const state = window.localStorage.getItem('her_verification_flow_state')
    return state === null
  })
}

/**
 * 获取锁定状态
 */
export async function getVerificationState(page: any): Promise<any> {
  return await page.evaluate(() => {
    const state = window.localStorage.getItem('her_verification_flow_state')
    return state ? JSON.parse(state) : null
  })
}