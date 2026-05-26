import { gatewayJson, queryString } from '@/lib/api/client'
import { getProfileId, getUserId } from '@/lib/auth/session'

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
  return {
    challenge_token: response.challenge_token ?? response.challenge?.challenge_token,
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
  const userId = getUserId()
  if (!userId) throw new Error('请先登录')

  const videoBase64 =
    params.videoBase64 ??
    (process.env.NODE_ENV === 'test' ? STUB_VIDEO_BASE64 : undefined)
  if (!videoBase64) {
    throw new Error('请先录制视频后再提交')
  }

  return gatewayJson<{ submission?: VerificationSubmission }>(
    '/v1/verifications/live-video-submissions',
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        profile_id: getProfileId(),
        video_base64: videoBase64,
        file_name: params.fileName || 'verification-recording.webm',
        content_type: params.contentType || 'video/webm',
        challenge_token: params.challengeToken,
        challenge_phrase: params.challengePhrase,
        metadata: { action_result: [], source: 'her-app' },
      }),
    },
  )
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
