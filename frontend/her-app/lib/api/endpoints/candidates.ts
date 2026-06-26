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

export type CandidateXiaoyaAnalysisResponse = {
  candidate_id?: number
  xiaoya_analysis?: string | null
  xiaoya_analysis_structured?: {
    summary?: string
    risk_point?: string
    first_question?: string
  } | null
}

export async function fetchCandidateDetail(params: {
  candidateId: string | number
  sessionId?: string | null
  recommendationId?: string | number | null
  caseId?: string
  cardId?: string  // 新增：支持通过card_id验证权限
}) {
  return gatewayJson<CandidateDetailResponse>(
    `/v1/candidates/${encodeURIComponent(String(params.candidateId))}${queryString({
      session_id: params.sessionId ?? undefined,
      recommendation_id: params.recommendationId ?? undefined,
      case_id: params.caseId ?? undefined,
      card_id: params.cardId ?? undefined,  // 新增：传递card_id参数
    })}`,
  )
}

export async function fetchCandidateXiaoyaAnalysis(params: {
  candidateId: string | number
  sessionId: string
  refreshKey?: string | number
  signal?: AbortSignal // Support request cancellation
}) {
  return gatewayJson<CandidateXiaoyaAnalysisResponse>(
    `/v1/candidates/${encodeURIComponent(String(params.candidateId))}/xiaoya-analysis${queryString({
      session_id: params.sessionId,
      refresh_key: params.refreshKey ?? undefined,
    })}`,
    { signal: params.signal }, // Pass AbortSignal to fetch
  )
}
