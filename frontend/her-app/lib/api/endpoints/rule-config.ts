import { gatewayJson } from '@/lib/api/client'

export type RuleConfigActiveItem = {
  version_id: string
  slice_id: string
  params: Record<string, unknown>
  schema_version?: string
  status?: string
}

export type ExperimentBucketMember = {
  profile_id: number
  bucket_key: string
  updated_by?: string
  updated_at?: string
}

export type DecisionTrace = {
  recommendation_id?: number
  reason_codes?: string[]
  reason_code_labels?: Array<{ code: string; human_label?: string }>
  effective_params?: Record<string, unknown>
  has_effective_params?: boolean
}

export async function fetchActiveRuleConfig() {
  return gatewayJson<{ active: RuleConfigActiveItem[] }>('/v1/ops/rule-config/active', {
    includeAuth: true,
  })
}

export async function fetchExperimentBucketMembers(limit = 50) {
  const query = `?limit=${encodeURIComponent(String(limit))}`
  return gatewayJson<{ members: ExperimentBucketMember[] }>(
    `/v1/ops/rule-config/experiment-members${query}`,
    { includeAuth: true },
  )
}

export async function upsertExperimentBucketMember(payload: {
  profile_id: number
  bucket_key: string
}) {
  return gatewayJson<{ member: ExperimentBucketMember }>('/v1/ops/rule-config/experiment-members', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(payload),
  })
}

export async function fetchRecommendationDecisionTrace(recommendationId: number | string) {
  return gatewayJson<{ decision_trace: DecisionTrace }>(
    `/v1/ops/recommendations/${encodeURIComponent(String(recommendationId))}/decision-trace`,
    { includeAuth: true },
  )
}

export async function activateRuleConfigVersion(versionId: string) {
  return gatewayJson<{ version: Record<string, unknown> }>(
    `/v1/ops/rule-config/versions/${encodeURIComponent(versionId)}/activate`,
    { method: 'POST', includeAuth: true },
  )
}

export async function createRuleConfigAssignment(payload: {
  assignment_id: string
  version_id: string
  slice_id: string
  scope_type: string
  scope_key: string
  priority?: number
}) {
  return gatewayJson<{ assignment: Record<string, unknown> }>('/v1/ops/rule-config/assignments', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(payload),
  })
}
