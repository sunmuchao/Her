import { gatewayJson } from '@/lib/api/client'

export type VerificationNotification = {
  notification_id: string
  user_id: string
  profile_id: number
  submission_id: string
  notification_type: 'verification_result'
  decision: 'approve' | 'reject' | 'request_resubmission'
  message: string
  created_at: string
  read?: boolean
}

export type SendNotificationParams = {
  userId: string
  profileId: number
  submissionId: string
  decision: 'approve' | 'reject' | 'request_resubmission'
  message: string
  channels?: ('in_app' | 'sms' | 'email')[]
}

/**
 * 发送审核结果通知
 */
export async function sendVerificationNotification(params: SendNotificationParams): Promise<{ notification_id: string }> {
  return gatewayJson<{ notification_id: string }>(
    '/v1/notifications/verification-result',
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        user_id: params.userId,
        profile_id: params.profileId,
        submission_id: params.submissionId,
        decision: params.decision,
        message: params.message,
        channels: params.channels || ['in_app'],
      }),
    },
  )
}

/**
 * 获取用户的审核通知列表
 */
export async function fetchVerificationNotifications(userId: string): Promise<VerificationNotification[]> {
  const response = await gatewayJson<{ notifications?: VerificationNotification[] }>(
    `/v1/notifications/verification?user_id=${userId}`,
    { includeAuth: true },
  )

  return response.notifications || []
}