import { sendVerificationNotification } from '@/lib/api/endpoints/verification-notification'

type NotificationParams = {
  userId?: string
  profileId: number
  submissionId: string
  decision: 'approve' | 'reject' | 'request_resubmission'
  approvedValue?: string
  requestedDocuments?: string[]
  reviewNote?: string
}

/**
 * 生成审核结果通知消息
 */
function generateNotificationMessage(params: NotificationParams): string {
  switch (params.decision) {
    case 'approve':
      return `您的学历认证已通过审核，认证学历为：${params.approvedValue || '已确认'}。感谢您的配合！`
    case 'reject':
      return `您的学历认证审核未通过。原因：${params.reviewNote || '材料不符合要求'}。请重新提交认证材料。`
    case 'request_resubmission':
      const docs = params.requestedDocuments?.join('、') || '补充材料'
      return `您的学历认证需要补充材料。请补充以下文件：${docs}。`
    default:
      return '您的学历认证状态已更新。'
  }
}

/**
 * 发送审核结果通知（自动调用）
 */
export async function notifyVerificationResult(params: NotificationParams): Promise<void> {
  if (!params.userId) {
    // 如果没有user_id，无法发送通知
    console.warn('无法发送通知：缺少user_id')
    return
  }

  const message = generateNotificationMessage(params)

  try {
    await sendVerificationNotification({
      userId: params.userId,
      profileId: params.profileId,
      submissionId: params.submissionId,
      decision: params.decision,
      message,
      channels: ['in_app'], // 默认只发送站内通知，后续可扩展短信/邮件
    })
    console.log('审核通知已发送')
  } catch (error) {
    // 通知发送失败不影响审核结果
    console.error('审核通知发送失败:', error)
  }
}