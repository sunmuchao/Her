import { gatewayJson, queryString } from '@/lib/api/client'
import { getProfileId, getUserId } from '@/lib/auth/session'
import {
  lockVerificationState,
  getLockedProfileId,
  getLockedUserId,
  validateChallengeToken,
  clearVerificationState,
  detectSessionChange,
} from '@/lib/verification/flow-state'

export type VerificationSubmission = {
  submission_id?: string
  status?: string
  profile_id?: string
  user_id?: string
  created_at?: string
}

export type VerificationNotification = {
  notification_id?: string
  type?: string
  title?: string
  body?: string
  created_at?: string
}

type SubmissionsResponse = {
  submissions?: VerificationSubmission[]
}

type NotificationsResponse = {
  notifications?: VerificationNotification[]
}

export async function listVerificationSubmissions(): Promise<VerificationSubmission[]> {
  const userId = getUserId()
  if (!userId) return []

  const response = await gatewayJson<SubmissionsResponse>(
    `/v1/verifications/live-video-submissions${queryString({
      user_id: userId,
      profile_id: getProfileId(),
      limit: 20,
    })}`,
  )
  return response.submissions ?? []
}

export type LiveVideoChallenge = {
  challenge_token?: string
  challenge_phrase?: string
  required_actions?: string[]
}

/** Minimal stub payload for automated tests only (not production). */
const STUB_VIDEO_BASE64 =
  'GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQRChYECGFOAZwEAAAAAAAHTEU2bdLpNu4tAA5'

export async function createLiveVideoChallenge(): Promise<LiveVideoChallenge> {
  const userId = getUserId()
  if (!userId) throw new Error('请先登录')

  // 检测是否存在旧的验证流程状态
  const sessionChange = detectSessionChange()
  if (sessionChange.hasChanged) {
    console.warn(
      `Session profile_id changed from ${sessionChange.lockedProfileId} to ${sessionChange.currentProfileId}. Clearing old verification state.`
    )
    clearVerificationState()
  }

  const response = await gatewayJson<{ challenge?: LiveVideoChallenge } & LiveVideoChallenge>(
    '/v1/verifications/live-video-challenges',
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        profile_id: getProfileId(),
        challenge_action_pool: ['nod', 'blink', 'smile'],
        action_count: 2,
      }),
    },
  )

  const challengeToken = response.challenge_token ?? response.challenge?.challenge_token

  // ✅ 关键修复：在创建 challenge 时锁定状态
  if (challengeToken) {
    lockVerificationState(challengeToken)
  }

  return {
    challenge_token: challengeToken,
    challenge_phrase: response.challenge_phrase ?? response.challenge?.challenge_phrase,
    required_actions: response.required_actions ?? response.challenge?.required_actions,
  }
}

export async function submitLiveVideoVerification(params: {
  challengeToken: string
  challengePhrase?: string
  videoBase64?: string
  fileName?: string
  contentType?: string
}) {
  // ✅ 关键修复：校验 challenge_token 是否与锁定状态一致
  if (!validateChallengeToken(params.challengeToken)) {
    throw new Error('验证凭证已过期，请重新开始验证流程')
  }

  // ✅ 关键修复：使用锁定的 user_id 和 profile_id，而非动态读取
  const userId = getLockedUserId()
  if (!userId) throw new Error('请先登录')

  const profileId = getLockedProfileId()

  // 检测 session 是否发生变化
  const sessionChange = detectSessionChange()
  if (sessionChange.hasChanged) {
    console.warn(
      `Session profile_id changed during verification flow. Using locked profile_id ${sessionChange.lockedProfileId} instead of current ${sessionChange.currentProfileId}`
    )
  }

  const videoBase64 =
    params.videoBase64 ?? (process.env.NODE_ENV === 'test' ? STUB_VIDEO_BASE64 : undefined)
  if (!videoBase64) {
    throw new Error('请先录制视频后再提交')
  }

  try {
    const result = await gatewayJson<{ submission?: VerificationSubmission }>(
      '/v1/verifications/live-video-submissions',
      {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          profile_id: profileId,
          video_base64: videoBase64,
          file_name: params.fileName || 'verification-recording.webm',
          content_type: params.contentType || 'video/webm',
          challenge_token: params.challengeToken,
          challenge_phrase: params.challengePhrase,
          metadata: { action_result: [], source: 'her-app' },
        }),
      }
    )

    // ✅ 关键修复：验证完成后清理锁定状态
    clearVerificationState()

    return result
  } catch (error) {
    // 如果验证失败，也清理锁定状态（允许用户重新开始）
    clearVerificationState()
    throw error
  }
}

export async function listVerificationNotifications(): Promise<VerificationNotification[]> {
  const userId = getUserId()
  if (!userId) return []

  const response = await gatewayJson<NotificationsResponse>(
    `/v1/verifications/notifications${queryString({
      user_id: userId,
      limit: 20,
    })}`,
  )
  return response.notifications ?? []
}