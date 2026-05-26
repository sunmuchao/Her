import { gatewayJson, queryString } from '@/lib/api/client'
import type { TrustSummary } from '@/lib/api/endpoints/trust'

export type CandidateDetailResponse = {
  candidate_id?: number
  profile_id?: number
  detail_source?: 'discovery' | 'profile' | string
  detail_view?: {
    hero?: { headline?: string }
    photo_gallery?: Array<{ url?: string; image_url?: string }>
    self_reported_sections?: Array<{ items?: string[] }>
    verified_sections?: Array<{ items?: string[] }>
    matchmaker_notes?: string[]
    caution_sections?: Array<{ items?: string[] }>
  }
  profile_facts?: Record<string, unknown>
  trust_summary?: TrustSummary
  explain?: {
    source_map?: Record<string, string>
    runtime_explanation?: unknown
  }
}

export async function fetchCandidateDetail(params: {
  candidateId: string | number
  sessionId?: string | null
  recommendationId?: string | number | null
}) {
  return gatewayJson<CandidateDetailResponse>(
    `/v1/candidates/${encodeURIComponent(String(params.candidateId))}${queryString({
      session_id: params.sessionId ?? undefined,
      recommendation_id: params.recommendationId ?? undefined,
    })}`,
  )
}
