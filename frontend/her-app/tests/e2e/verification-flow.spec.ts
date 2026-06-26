/**
 * 视频验证流程 E2E 测试
 *
 * 测试场景：
 * 1. 正常流程：创建 challenge → 录制视频 → 提交验证 → 成功
 * 2. session 变化：创建 challenge → 切换 profile → 提交验证 → 使用锁定值成功
 * 3. token 过期：创建 challenge → 等待15分钟 → 提交验证 → 提示过期
 * 4. 验证失败：创建 challenge → 提交失败 → 自动清理状态
 */

import { expect, test } from '@playwright/test'
import {
  loginAsUser,
  createChallenge,
  submitVerification,
  getSubmitRequest,
  changeSessionProfileId,
  expireVerificationState,
  mockSubmitFailure,
  isVerificationStateCleared,
  getVerificationState,
} from './helpers/verification'

test.describe('视频验证流程', () => {
  test.setTimeout(90000) // 90秒超时

  test('正常流程：创建验证并成功提交', async ({ page }) => {
    // 1. 登录
    await loginAsUser(page, 'test-user-123', { profileId: 123 })

    // 2. 导航到验证页面
    await page.goto('/verification')

    // 3. 创建 challenge
    await createChallenge(page)

    // 4. 等待 challenge_token 返回
    const challengeRequest = page.waitForRequest(
      (req) =>
        req.url().includes('/v1/verifications/live-video-challenges') &&
        req.method() === 'POST'
    )
    await challengeRequest

    // 5. 模拟录制视频（使用 stub）
    await page.evaluate(() => {
      window.localStorage.setItem('test_video_base64', 'STUB_VIDEO_BASE64')
    })

    // 6. 提交验证
    await submitVerification(page)

    // 7. 等待提交请求
    const request = await getSubmitRequest(page)
    const body = request.postDataJSON()

    // 8. 验证请求体包含锁定的 profile_id
    expect(body.profile_id).toBeDefined()
    expect(body.challenge_token).toBeDefined()

    // 9. 等待成功响应
    await page.waitForSelector('[data-testid="verification-success"]')

    // 10. 验证锁定状态已清理
    const isCleared = await isVerificationStateCleared(page)
    expect(isCleared).toBe(true)
  })

  test('session 变化：使用锁定值提交成功', async ({ page }) => {
    // 1. 登录并创建 challenge（profile_id = 123）
    await loginAsUser(page, 'test-user-123', { profileId: 123 })
    await page.goto('/verification')
    await createChallenge(page)

    // 2. 模拟 session 变化（切换到 profile_id = 456）
    await changeSessionProfileId(page, 456)

    // 3. 提交验证（应使用锁定的 profile_id = 123）
    await submitVerification(page)

    // 4. 验证请求体使用的是锁定值
    const request = await getSubmitRequest(page)
    const body = request.postDataJSON()
    expect(body.profile_id).toBe(123) // 锁定值，而非当前值 456

    // 5. 验证成功
    await page.waitForSelector('[data-testid="verification-success"]')
  })

  test('token 过期：提示用户重新开始', async ({ page }) => {
    // 1. 创建 challenge（模拟 16 分钟前创建）
    await loginAsUser(page, 'test-user-123', { profileId: 123 })
    await page.goto('/verification')
    await createChallenge(page)

    // 2. 模拟状态过期
    await expireVerificationState(page)

    // 3. 提交验证
    await submitVerification(page)

    // 4. 等待错误提示
    const errorMsg = await page.waitForSelector('[data-testid="error-message"]')
    const text = await errorMsg.textContent()
    expect(text).toContain('验证凭证已过期')
  })

  test('验证失败：自动清理状态', async ({ page }) => {
    // 1. 创建 challenge
    await loginAsUser(page, 'test-user-123', { profileId: 123 })
    await page.goto('/verification')
    await createChallenge(page)

    // 2. 模拟提交失败（使用错误的 video_base64）
    await mockSubmitFailure(page, '视频格式错误')

    // 3. 提交验证
    await submitVerification(page)

    // 4. 等待失败响应
    await page.waitForSelector('[data-testid="error-message"]')

    // 5. 验证锁定状态已清理
    const isCleared = await isVerificationStateCleared(page)
    expect(isCleared).toBe(true)
  })
})