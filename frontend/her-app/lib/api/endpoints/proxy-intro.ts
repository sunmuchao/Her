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
      age_bracket?: string
      city?: string
      occupation?: string
      education?: string
      relationship_goal?: string
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

export async function openProxyIntroChat(params: { caseId: string; source?: string }) {
  return gatewayJson<{
    case?: ProxyIntroCase
    conversation?: { conversation_id?: string; channel_key?: string }
  }>(`/v1/proxy-intro/cases/${encodeURIComponent(params.caseId)}/open-chat`, {
    method: 'POST',
    body: JSON.stringify({ source: params.source }),
  })
}
