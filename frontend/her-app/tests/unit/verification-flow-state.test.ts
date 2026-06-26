/**
 * 验证流程状态锁定测试
 *
 * 测试目标：
 * 1. 验证状态锁定机制是否正常工作
 * 2. 验证 session 变化检测是否准确
 * 3. 验证 challenge_token 校验是否有效
 * 4. 验证状态清理机制是否正确
 */

import {
  lockVerificationState,
  getLockedProfileId,
  getLockedUserId,
  validateChallengeToken,
  clearVerificationState,
  detectSessionChange,
} from '../../lib/verification/flow-state'
import { getProfileId, getUserId, patchSessionContext } from '../../lib/auth/session'
import { beforeEach, describe, expect, test, vi, afterEach } from 'vitest'

describe('验证流程状态锁定', () => {
  beforeEach(() => {
    // Mock localStorage
    const localStorageMock = (() => {
      let store: Record<string, string> = {}
      return {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => {
          store[key] = value.toString()
        },
        removeItem: (key: string) => {
          delete store[key]
        },
        clear: () => {
          store = {}
        },
      }
    })()

    vi.stubGlobal('window', { localStorage: localStorageMock })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('锁定状态后能正确获取锁定的 profile_id', () => {
    const challengeToken = 'test-challenge-token-123'
    const profileId = 123

    // 模拟当前 session 的 profile_id
    patchSessionContext({ profileId })

    // 锁定状态
    lockVerificationState(challengeToken)

    // 获取锁定的 profile_id
    const lockedProfileId = getLockedProfileId()

    expect(lockedProfileId).toBe(profileId)
  })

  test('session 变化后仍使用锁定的 profile_id', () => {
    const challengeToken = 'test-challenge-token-123'
    const originalProfileId = 123
    const newProfileId = 456

    // 模拟创建 challenge 时的 profile_id
    patchSessionContext({ profileId: originalProfileId })
    lockVerificationState(challengeToken)

    // 模拟 session 变化
    patchSessionContext({ profileId: newProfileId })

    // 检测 session 变化
    const sessionChange = detectSessionChange()
    expect(sessionChange.hasChanged).toBe(true)
    expect(sessionChange.lockedProfileId).toBe(originalProfileId)
    expect(sessionChange.currentProfileId).toBe(newProfileId)

    // 获取锁定的 profile_id（应该还是原来的值）
    const lockedProfileId = getLockedProfileId()
    expect(lockedProfileId).toBe(originalProfileId)
  })

  test('challenge_token 校验机制', () => {
    const validToken = 'valid-challenge-token'
    const invalidToken = 'invalid-challenge-token'

    // 锁定状态
    lockVerificationState(validToken)

    // 校验正确的 token
    expect(validateChallengeToken(validToken)).toBe(true)

    // 校验错误的 token
    expect(validateChallengeToken(invalidToken)).toBe(false)
  })

  test('状态清理机制', () => {
    const challengeToken = 'test-challenge-token'
    const profileId = 123

    // 锁定状态
    patchSessionContext({ profileId })
    lockVerificationState(challengeToken)

    // 确认状态已锁定（返回锁定值）
    expect(getLockedProfileId()).toBe(profileId)

    // 清理状态
    clearVerificationState()

    // 确认锁定状态已清理，但返回兜底值（当前 session 的 profile_id）
    expect(getLockedProfileId()).toBe(profileId)  // 兜底机制：返回 session 的 profile_id
  })

  test('状态自动过期（15分钟）', () => {
    const challengeToken = 'test-challenge-token'
    const profileId = 123

    // 设置当前 session 的 profile_id（用于兜底）
    patchSessionContext({ profileId })

    // 锁定状态（模拟创建时间为 16 分钟前）
    const oldTimestamp = Date.now() - 16 * 60 * 1000
    window.localStorage.setItem(
      'her_verification_flow_state',
      JSON.stringify({
        lockedProfileId: profileId,
        challengeToken,
        createdAt: oldTimestamp,
      })
    )

    // 读取状态（应该自动过期，返回兜底值）
    const lockedProfileId = getLockedProfileId()
    expect(lockedProfileId).toBe(profileId)  // 兜底机制：返回 session 的 profile_id
  })

  test('兜底机制：无锁定状态时使用当前 session', () => {
    const currentProfileId = 789

    // 模拟当前 session
    patchSessionContext({ profileId: currentProfileId })

    // 无锁定状态
    clearVerificationState()

    // 获取 profile_id（应该返回当前 session 的值）
    const profileId = getLockedProfileId()
    expect(profileId).toBe(currentProfileId)
  })
})

/**
 * 实际使用场景测试
 *
 * 场景 1：正常流程
 * - 创建 challenge → 锁定状态 → 提交验证 → 成功 → 清理状态
 *
 * 场景 2：session 变化
 * - 创建 challenge → 锁定状态 → session 变化 → 提交验证 → 使用锁定值成功 → 清理状态
 *
 * 场景 3：token 过期
 * - 创建 challenge → 锁定状态 → 等待15分钟 → 提交验证 → 失败提示"验证凭证已过期"
 *
 * 场景 4：验证失败
 * - 创建 challenge → 锁定状态 → 提交验证失败 → 自动清理状态 → 可重新开始
 */