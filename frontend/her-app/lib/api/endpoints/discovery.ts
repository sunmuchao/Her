import { gatewayJson } from '@/lib/api/client'
import type {
  DiscoverySessionResponse,
  DiscoverySessionListResponse,
  DiscoveryTurnAttachment,
  DiscoveryTurnClientContext,
} from '@/lib/types/discovery'

export async function createDiscoverySession(params: { profileId: number }) {
  return gatewayJson<DiscoverySessionResponse>('/v1/discovery/sessions', {
    method: 'POST',
    body: JSON.stringify({
      profile_id: params.profileId,
    }),
  })
}

export async function getDiscoverySession(sessionId: string) {
  return gatewayJson<DiscoverySessionResponse>(`/v1/discovery/sessions/${encodeURIComponent(sessionId)}`)
}

export async function submitDiscoveryTurn(params: {
  sessionId: string
  userMessage?: string
  actionId?: string
  text?: string
  attachments?: DiscoveryTurnAttachment[]
  clientContext?: DiscoveryTurnClientContext
}) {
  const text = params.text ?? params.userMessage
  return gatewayJson<DiscoverySessionResponse>('/v1/discovery/turns', {
    method: 'POST',
    body: JSON.stringify(
      params.actionId
        ? {
            session_id: params.sessionId,
            action_id: params.actionId,
          }
        : {
            session_id: params.sessionId,
            message: {
              text,
              attachments: params.attachments,
            },
            client_context: params.clientContext,
          },
    ),
  })
}

export async function confirmDiscoveryProfileUpdate(sessionId: string, requestId: string) {
  return gatewayJson<{ ok?: boolean; request_id?: string; status?: string }>(
    `/v1/discovery/sessions/${encodeURIComponent(sessionId)}/profile-updates/${encodeURIComponent(requestId)}/confirm`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function rejectDiscoveryProfileUpdate(sessionId: string, requestId: string) {
  return gatewayJson<{ ok?: boolean; request_id?: string; status?: string }>(
    `/v1/discovery/sessions/${encodeURIComponent(sessionId)}/profile-updates/${encodeURIComponent(requestId)}/reject`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function expressDiscoveryCandidateInterest(params: {
  sessionId: string
  candidateId: string | number
}) {
  return gatewayJson<{
    ok?: boolean
    session_id?: string
    candidate_id?: number
    subscription_id?: string
    case?: Record<string, unknown>
  }>(
    `/v1/discovery/sessions/${encodeURIComponent(params.sessionId)}/candidates/${encodeURIComponent(String(params.candidateId))}/express-interest`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function recordDiscoveryCandidateQuickPass(params: {
  sessionId: string
  candidateId: string | number
}) {
  return gatewayJson<{
    ok?: boolean
    session_id?: string
    candidate_id?: number
    event_type?: string
    deduped?: boolean
  }>(
    `/v1/discovery/sessions/${encodeURIComponent(params.sessionId)}/candidates/${encodeURIComponent(String(params.candidateId))}/quick-pass`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function recordDiscoveryCandidateExplicitDislike(params: {
  sessionId: string
  candidateId: string | number
}) {
  return gatewayJson<{
    ok?: boolean
    session_id?: string
    candidate_id?: number
    event_type?: string
    deduped?: boolean
  }>(
    `/v1/discovery/sessions/${encodeURIComponent(params.sessionId)}/candidates/${encodeURIComponent(String(params.candidateId))}/explicit-dislike`,
    { method: 'POST', body: JSON.stringify({}) },
  )
}

export async function recordDiscoveryCandidateTelemetry(params: {
  sessionId: string
  candidateId: string | number
  telemetry: {
    card_impression_count?: number
    card_visible_duration_ms?: number
    detail_view_duration_ms?: number
    photo_swipe_count?: number
    return_view_count?: number
  }
}) {
  return gatewayJson<{
    ok?: boolean
    session_id?: string
    candidate_id?: number
    search_run_id?: string
    telemetry?: Record<string, number>
    quick_bounce?: boolean
    ignored?: boolean
  }>(
    `/v1/discovery/sessions/${encodeURIComponent(params.sessionId)}/candidates/${encodeURIComponent(String(params.candidateId))}/telemetry`,
    {
      method: 'POST',
      body: JSON.stringify({
        telemetry: params.telemetry,
      }),
    },
  )
}

export async function fetchDiscoverySessionList(params: {
  profileId: number
  limit?: number
}) {
  const limitParam = params.limit ?? 20
  return gatewayJson<DiscoverySessionListResponse>(
    `/v1/discovery/sessions?profile_id=${encodeURIComponent(params.profileId)}&limit=${encodeURIComponent(limitParam)}`,
  )
}
