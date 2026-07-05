import { gatewayJson } from '@/lib/api/client'
import type { CandidatePreview } from '@/lib/types/candidate'
import type { DiscoverySessionResponse, DiscoverySessionListResponse } from '@/lib/types/discovery'

export type DiscoveryPhotoSearchMode = 'auto' | 'face' | 'style' | 'celebrity' | 'hybrid'

export type DiscoveryPhotoSearchResponse = {
  trace_id?: string
  task?: {
    status?: 'succeeded' | 'failed'
    stage?: string
  }
  intent?: {
    mode?: DiscoveryPhotoSearchMode
    intent_type?: string
    query_text?: string
    celebrity_name?: string | null
    attribute_filters?: Record<string, unknown>
    hard_filters?: Record<string, unknown>
    confidence?: number
    routing_reasons?: string[]
    image_understanding?: Record<string, unknown>
  }
  result_count?: number
  search_type?: string
  query_text?: string
  image_source_present?: boolean
  results?: CandidatePreview[]
  session_sync?: {
    success?: boolean
    session_id?: string
    timeline_count?: number
    appended_result_count?: number
  } | null
}

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
}) {
  return gatewayJson<DiscoverySessionResponse>(
    `/v1/discovery/sessions/${params.sessionId}/turns`,
    {
      method: 'POST',
      body: JSON.stringify(
        params.actionId
          ? { action_id: params.actionId }
          : { user_message: params.userMessage },
      ),
    },
  )
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

export async function searchDiscoveryByPhoto(params: {
  profileId: number
  mode?: DiscoveryPhotoSearchMode
  sessionId?: string
  imageSource?: string
  queryText?: string
  celebrityName?: string
  topK?: number
  attributeFilters?: Record<string, unknown>
}) {
  return gatewayJson<DiscoveryPhotoSearchResponse>('/v1/discovery/photo-search', {
    method: 'POST',
    body: JSON.stringify({
      profile_id: params.profileId,
      session_id: params.sessionId,
      mode: params.mode,
      image_source: params.imageSource,
      query_text: params.queryText,
      celebrity_name: params.celebrityName,
      top_k: params.topK,
      attribute_filters: params.attributeFilters,
    }),
  })
}
