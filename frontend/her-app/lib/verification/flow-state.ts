/**
 * 验证流程状态管理器
 *
 * 设计目标：
 * 1. 在验证流程开始时锁定关键状态（profile_id, user_id）
 * 2. 防止在验证过程中因 session 变化导致状态不一致
 * 3. 验证完成后自动清理锁定状态
 *
 * 根因分析：用户在创建 challenge 和提交验证之间，localStorage 中的 profile_id 可能发生变化
 * 解决方案：在创建 challenge 时锁定 profile_id，提交时使用锁定值而非动态读取
 */

import { getProfileId, getUserId } from '@/lib/auth/session'

const VERIFICATION_STATE_KEY = 'her_verification_flow_state'

/**
 * 验证流程锁定状态
 */
type VerificationFlowState = {
  /** 创建 challenge 时的 profile_id */
  lockedProfileId?: number
  /** 创建 challenge 时的 user_id */
  lockedUserId?: string
  /** challenge_token */
  challengeToken?: string
  /** 创建时间（用于过期检测） */
  createdAt?: number
}

/**
 * 验证流程状态过期时间（15分钟，与 challenge_token TTL 一致）
 */
const VERIFICATION_STATE_TTL_MS = 15 * 60 * 1000

/**
 * 读取验证流程锁定状态
 */
function readVerificationState(): VerificationFlowState {
  if (typeof window === 'undefined') {
    return {}
  }
  const raw = window.localStorage.getItem(VERIFICATION_STATE_KEY)
  if (!raw) {
    return {}
  }
  try {
    const state = JSON.parse(raw) as VerificationFlowState
    // 检查是否过期
    if (state.createdAt && Date.now() - state.createdAt > VERIFICATION_STATE_TTL_MS) {
      clearVerificationState()
      return {}
    }
    return state
  } catch {
    clearVerificationState()
    return {}
  }
}

/**
 * 写入验证流程锁定状态
 */
function writeVerificationState(state: VerificationFlowState) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(VERIFICATION_STATE_KEY, JSON.stringify(state))
}

/**
 * 锁定验证流程状态
 *
 * 在创建 challenge 时调用，记录当前的 profile_id 和 user_id
 */
export function lockVerificationState(challengeToken: string): VerificationFlowState {
  const profileId = getProfileId()
  const userId = getUserId()

  const state: VerificationFlowState = {
    lockedProfileId: profileId,
    lockedUserId: userId,
    challengeToken,
    createdAt: Date.now(),
  }

  writeVerificationState(state)
  return state
}

/**
 * 获取锁定的 profile_id
 *
 * 在提交验证时调用，使用锁定值而非动态读取
 * 如果不存在锁定状态，则返回当前 session 的 profile_id（兜底）
 */
export function getLockedProfileId(): number | undefined {
  const state = readVerificationState()

  // 如果有锁定值，优先使用锁定值
  if (state.lockedProfileId !== undefined) {
    return state.lockedProfileId
  }

  // 兜底：返回当前 session 的 profile_id
  return getProfileId()
}

/**
 * 获取锁定的 user_id
 *
 * 在提交验证时调用，使用锁定值而非动态读取
 * 如果不存在锁定状态，则返回当前 session 的 user_id（兜底）
 */
export function getLockedUserId(): string | undefined {
  const state = readVerificationState()

  // 如果有锁定值，优先使用锁定值
  if (state.lockedUserId) {
    return state.lockedUserId
  }

  // 兜底：返回当前 session 的 user_id
  return getUserId()
}

/**
 * 校验 challenge_token 是否与锁定状态一致
 *
 * 防止用户使用旧的 challenge_token
 */
export function validateChallengeToken(challengeToken: string): boolean {
  const state = readVerificationState()

  // 如果锁定状态不存在，允许任何 token（兜底）
  if (!state.challengeToken) {
    return true
  }

  // 校验 token 是否一致
  return state.challengeToken === challengeToken
}

/**
 * 清理验证流程锁定状态
 *
 * 在验证完成后调用，释放锁定状态
 */
export function clearVerificationState() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(VERIFICATION_STATE_KEY)
}

/**
 * 检测 session 中的 profile_id 是否发生变化
 *
 * 如果发生变化，建议重新创建 challenge
 */
export function detectSessionChange(): {
  hasChanged: boolean
  lockedProfileId?: number
  currentProfileId?: number
} {
  const state = readVerificationState()
  const currentProfileId = getProfileId()

  // 如果没有锁定状态，认为没有变化
  if (state.lockedProfileId === undefined) {
    return { hasChanged: false }
  }

  // 检测是否变化
  const hasChanged = state.lockedProfileId !== currentProfileId

  return {
    hasChanged,
    lockedProfileId: state.lockedProfileId,
    currentProfileId,
  }
}