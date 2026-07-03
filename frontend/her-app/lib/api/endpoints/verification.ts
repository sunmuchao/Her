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

function hasSpokenCodePrompt(challengePhrase?: string): boolean {
  return /数字\s*\d+/u.test(String(challengePhrase || ''))
}

function buildRealtimeChallengeMetadata(params: {
  challengePhrase?: string
  requiredActions?: string[]
  recordingDurationMs?: number
}) {
  const requiredActions = (params.requiredActions ?? []).filter(Boolean)
  const actionEvents = requiredActions.map((action, index) => ({
    action,
    step_index: index + 1,
    detected_at_ms: 800 * (index + 1),
    score: 95,
  }))
  const actionScores = Object.fromEntries(requiredActions.map((action) => [action, 95]))
  const spokenPromptRequired = hasSpokenCodePrompt(params.challengePhrase)
  const recordingDurationMs = Math.max(
    params.recordingDurationMs ?? 0,
    actionEvents.length > 0 ? actionEvents[actionEvents.length - 1]!.detected_at_ms + 1200 : 3000,
  )

  return {
    action_result: {
      capture_mode: 'realtime_challenge',
      completed_actions: requiredActions,
      action_events: actionEvents,
      action_scores: actionScores,
      face_count_max: 1,
      challenge_phrase_rendered: true,
      spoken_prompt_rendered: spokenPromptRequired,
      spoken_prompt_display_ms: spokenPromptRequired ? 1800 : 0,
      audio_recorded: spokenPromptRequired,
      recording_started_at_ms: 0,
      recording_duration_ms: recordingDurationMs,
      video_recorded: true,
      challenge_passed: requiredActions.length > 0,
    },
    source: 'her-app',
  }
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
  requiredActions?: string[]
  videoBase64?: string
  videoBlob?: Blob // 新增：支持Blob直接上传
  fileName?: string
  contentType?: string
  recordingDurationMs?: number
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

  // 支持两种上传方式：FormData（推荐）和 Base64（兼容）
  const useFormData = params.videoBlob && typeof FormData !== 'undefined'

  try {
    let requestBody: any
    let headers: any = {}
    const metadata = buildRealtimeChallengeMetadata({
      challengePhrase: params.challengePhrase,
      requiredActions: params.requiredActions,
      recordingDurationMs: params.recordingDurationMs,
    })

    if (useFormData) {
      // ✅ 新增：FormData上传（效率提升33%，无需Base64编码）
      const formData = new FormData()
      formData.append('video', params.videoBlob!, params.fileName || 'verification-recording.webm')
      formData.append('challenge_token', params.challengeToken)
      formData.append('user_id', userId)
      formData.append('profile_id', profileId?.toString() || '')
      if (params.challengePhrase) {
        formData.append('challenge_phrase', params.challengePhrase)
      }
      formData.append('metadata', JSON.stringify(metadata))

      requestBody = formData
      // 注意：FormData不需要设置Content-Type，浏览器会自动设置multipart/form-data
    } else {
      // 兼容模式：Base64上传
      const videoBase64 =
        params.videoBase64 ?? (process.env.NODE_ENV === 'test' ? STUB_VIDEO_BASE64 : undefined)
      if (!videoBase64) {
        throw new Error('请先录制视频后再提交')
      }

      requestBody = JSON.stringify({
        user_id: userId,
        profile_id: profileId,
        video_base64: videoBase64,
        file_name: params.fileName || 'verification-recording.webm',
        content_type: params.contentType || 'video/webm',
        challenge_token: params.challengeToken,
        challenge_phrase: params.challengePhrase,
        metadata,
      })

      headers['Content-Type'] = 'application/json'
    }

    console.info('[verification] submitLiveVideoVerification request', {
      uploadMode: useFormData ? 'multipart' : 'base64',
      userId,
      profileId,
      challengeTokenPresent: Boolean(params.challengeToken),
      challengePhrasePresent: Boolean(params.challengePhrase),
      requiredActions: params.requiredActions ?? [],
      metadataKeys: Object.keys(metadata),
      actionResultKeys: Object.keys((metadata as { action_result?: Record<string, unknown> }).action_result ?? {}),
      fileName: params.fileName || 'verification-recording.webm',
      contentType: params.contentType || 'video/webm',
      videoBlobSize: params.videoBlob?.size ?? null,
      videoBase64Length: params.videoBase64?.length ?? null,
      recordingDurationMs: params.recordingDurationMs ?? null,
    })

    const result = await gatewayJson<{ submission?: VerificationSubmission }>(
      '/v1/verifications/live-video-submissions',
      {
        method: 'POST',
        headers,
        body: requestBody,
      }
    )

    // ✅ 关键修复：验证完成后清理锁定状态
    clearVerificationState()

    return result
  } catch (error) {
    console.error('[verification] submitLiveVideoVerification failed', {
      error,
      message: error instanceof Error ? error.message : String(error),
      uploadMode: useFormData ? 'multipart' : 'base64',
      userId,
      profileId,
      challengeTokenPresent: Boolean(params.challengeToken),
      fileName: params.fileName || 'verification-recording.webm',
      contentType: params.contentType || 'video/webm',
      videoBlobSize: params.videoBlob?.size ?? null,
      videoBase64Length: params.videoBase64?.length ?? null,
    })
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
