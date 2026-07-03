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
  // The backend now generates verification notifications as part of the review flow.
  // Keep this function as a harmless compatibility wrapper so legacy callers do not fail.
  return Promise.resolve({
    notification_id: `backend-generated:${params.submissionId}`,
  })
}

/**
 * 获取用户的审核通知列表
 */
export async function fetchVerificationNotifications(params?: {
  userId?: string
  submissionId?: string
  limit?: number
}): Promise<VerificationNotification[]> {
  const query = new URLSearchParams()
  if (params?.userId) query.set('user_id', params.userId)
  if (params?.submissionId) query.set('submission_id', params.submissionId)
  if (params?.limit) query.set('limit', String(params.limit))
  const response = await gatewayJson<{ notifications?: VerificationNotification[] }>(
    `/v1/verifications/notifications${query.size ? `?${query.toString()}` : ''}`,
    { includeAuth: true },
  )

  return response.notifications || []
}
