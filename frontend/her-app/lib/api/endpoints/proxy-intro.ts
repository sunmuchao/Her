import { gatewayJson } from '@/lib/api/client'

export type ProxyIntroCase = {
  case_id: string
  case_status?: string
  stage_label?: string
  role?: 'requester' | 'candidate'
  counterpart_name?: string
  counterpart_profile_id?: number | null
  counterpart_image?: string | null
  counterpart_profile?: Record<string, unknown>
  can_reply?: boolean
  can_open_chat?: boolean
  main_conversation_id?: string | null
  reply_deadline_at?: string | null
  close_reason?: string | null
  created_at?: string
  updated_at?: string
  // 新增：用于提取 requester 信息
  outreach_payload?: {
    requester_summary?: {
      requester_name?: string
      age?: string  // 新增：实际年龄（如"28岁")
      age_bracket?: string  // 兼容性：年龄段（如"28岁"，实际年龄）
      city?: string
      occupation?: string
      education?: string
      relationship_goal?: string  // 中文关系目标（如"先谈恋爱")
      relationship_goal_raw?: string  // 英文原始值（如"dating")
      matched_on?: string[]  // 匹配点列表
      summary_text?: string
      avatar_url?: string
    }
  } | null
  requester_profile_snapshot?: {
    self_profile?: Record<string, unknown>
  } | null
}

export async function createProxyIntroRequest(params: {
  subscriptionId: string
  candidateId: number
  source?: string
}) {
  return gatewayJson<{ case?: ProxyIntroCase }>('/v1/proxy-intro/requests', {
    method: 'POST',
    body: JSON.stringify({
      subscription_id: params.subscriptionId,
      candidate_id: params.candidateId,
      source: params.source,
    }),
  })
}

export async function fetchMyProxyIntroCases() {
  return gatewayJson<{ cases?: ProxyIntroCase[]; count?: number }>('/v1/proxy-intro/cases/mine')
}

export async function replyProxyIntroCase(params: {
  caseId: string
  replyType: 'accepted' | 'declined'
  source?: string
}) {
  return gatewayJson<{ case?: ProxyIntroCase }>(
    `/v1/proxy-intro/cases/${encodeURIComponent(params.caseId)}/reply`,
    {
      method: 'POST',
      body: JSON.stringify({
        reply_type: params.replyType,
        source: params.source,
      }),
    },
  )
}

export async function markInterestCaseViewed(params: { caseId: string; source?: string }) {
  const result = await gatewayJson<{ case?: ProxyIntroCase; message?: string }>(
    `/v1/proxy-intro/cases/${encodeURIComponent(params.caseId)}/view`,
    {
      method: 'POST',
      body: JSON.stringify({
        source: params.source || 'detail_page',
      }),
    },
  )
  // 标记成功后触发事件，通知徽章计数刷新（与markRecommendationCardsRead保持一致）
  if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
    // 导入 RECOMMENDATION_READ_EVENT（共用同一个事件）
    const { RECOMMENDATION_READ_EVENT } = await import('@/lib/api/endpoints/recommendation')
    window.dispatchEvent(new CustomEvent(RECOMMENDATION_READ_EVENT, {
      detail: { caseId: params.caseId, source: params.source },
    }))
  }
  return result
}

export async function openProxyIntroChat(params: { caseId: string; source?: string }) {
  return gatewayJson<{
    case?: ProxyIntroCase
    conversation?: { conversation_id?: string; channel_key?: string }
  }>(`/v1/proxy-intro/cases/${encodeURIComponent(params.caseId)}/open-chat`, {
    method: 'POST',
    body: JSON.stringify({ source: params.source }),
  })
}

export async function closeProxyIntroCase(params: {
  caseId: string
  closeReason?: 'user_deleted' | 'requester_cancelled'
  source?: string
}) {
  return gatewayJson<{ case?: ProxyIntroCase; message?: string }>(
    `/v1/proxy-intro/cases/${encodeURIComponent(params.caseId)}/close`,
    {
      method: 'POST',
      body: JSON.stringify({
        close_reason: params.closeReason || 'user_deleted',
        source: params.source || 'relationships_page',
      }),
    },
  )
}
