export type VerificationItemView = {
  name: string
  status: 'verified' | 'pending' | 'action_required' | 'unverified'
  statusText: string
  description: string
  detail?: string
}

export type TrustHubVerificationItem = {
  item_id?: string
  title?: string
  status?: string
  status_label?: string
  review_eta?: string
  support_hint?: string
  failure_reason?: string
}

export type TrustHubPayload = {
  summary?: {
    pending_verification_count?: number
    pending_appeal_count?: number
    active_risk_count?: number
    notification_count?: number
  }
  verification_center?: {
    items?: TrustHubVerificationItem[]
  }
}

export function normalizeTrustVerificationStatus(status?: string): VerificationItemView['status'] {
  const text = (status || '').toLowerCase()
  if (['approved', 'verified', 'completed'].includes(text)) {
    return 'verified'
  }
  if (['submitted', 'in_progress', 'pending', 'under_review'].includes(text)) {
    return 'pending'
  }
  if (['action_required', 'rejected', 'resubmission_required', 'expired', 'awaiting_submission'].includes(text)) {
    return 'action_required'
  }
  return 'unverified'
}

export function mapTrustHubVerificationItems(
  items: TrustHubVerificationItem[] | undefined,
): VerificationItemView[] {
  return (items || []).map((item) => {
    const normalizedStatus = normalizeTrustVerificationStatus(item.status)
    return {
      name: item.title || '待认证项目',
      status: normalizedStatus,
      statusText:
        item.status_label ||
        (normalizedStatus === 'verified'
          ? '已认证'
          : normalizedStatus === 'pending'
            ? '审核中'
            : normalizedStatus === 'action_required'
              ? '待处理'
              : '未认证'),
      description: item.status_label || item.review_eta || item.support_hint || '等待进一步处理',
      detail: item.failure_reason || item.support_hint,
    }
  })
}

export function trustVerificationProgress(items: VerificationItemView[]) {
  const verifiedCount = items.filter((item) => item.status === 'verified').length
  const total = items.length
  const progress = total ? (verifiedCount / total) * 100 : 0
  return { verifiedCount, total, progress }
}

export function mapTrustHubPendingActions(
  items: TrustHubVerificationItem[] | undefined,
): Array<{ id: string; title: string; description: string; dueDate: string; type: 'verification' }> {
  return (items || [])
    .filter((item) => normalizeTrustVerificationStatus(item.status) !== 'verified')
    .map((item) => ({
      id: item.item_id || item.title || Math.random().toString(36).slice(2),
      title: item.title || '待补充材料',
      description: item.support_hint || item.status_label || '请补充相关信息',
      dueDate: item.review_eta || '请尽快处理',
      type: 'verification' as const,
    }))
}
