import { gatewayJson, queryString } from '@/lib/api/client'

export type RiskDashboardResponse = {
  dashboard?: Record<string, unknown>
}

export type ChatRiskCase = Record<string, unknown> & {
  risk_case_id?: string
  subject_user_id?: string
  status?: string
  severity?: string
  recommended_action?: string
  reason_text?: string
}

export type FraudNetwork = Record<string, unknown> & {
  subject_user_id?: string
  review_status?: string
  network_score?: number
}

export type RiskAppeal = Record<string, unknown> & {
  appeal_id?: number
  risk_case_id?: string
  appeal_status?: string
  reason_text?: string
}

export type RiskReport = Record<string, unknown> & {
  report_id?: number
  risk_case_id?: string
  report_type?: string
  reason_text?: string
}

export async function fetchRiskDashboard(days = 7) {
  return gatewayJson<RiskDashboardResponse>(
    `/v1/chat/risk-dashboard/weekly${queryString({ days })}`,
    { includeAuth: true },
  )
}

export async function fetchRiskCases(limit = 20, statuses?: string) {
  return gatewayJson<{ risk_cases?: ChatRiskCase[] }>(
    `/v1/chat/risk-cases${queryString({ limit, statuses })}`,
    { includeAuth: true },
  )
}

export async function reviewRiskCase(params: {
  riskCaseId: string
  status: string
  appliedAction?: string
  resolutionNote?: string
}) {
  return gatewayJson<{ risk_case?: ChatRiskCase }>(
    `/v1/chat/risk-cases/${encodeURIComponent(params.riskCaseId)}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        status: params.status,
        applied_action: params.appliedAction,
        resolution_note: params.resolutionNote,
      }),
    },
  )
}

export async function fetchFraudNetworks(limit = 20, minimumScore?: number) {
  return gatewayJson<{ fraud_networks?: FraudNetwork[] }>(
    `/v1/chat/fraud-networks${queryString({ limit, minimum_score: minimumScore })}`,
    { includeAuth: true },
  )
}

export async function fetchRiskAppeals(limit = 20, statuses?: string) {
  return gatewayJson<{ appeals?: RiskAppeal[] }>(
    `/v1/chat/risk-appeals${queryString({ limit, statuses })}`,
    { includeAuth: true },
  )
}

export async function reviewRiskAppeal(params: {
  appealId: number | string
  appealStatus: string
  resolutionNote?: string
}) {
  return gatewayJson<{ appeal?: RiskAppeal }>(
    `/v1/chat/risk-appeals/${encodeURIComponent(String(params.appealId))}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        appeal_status: params.appealStatus,
        resolution_note: params.resolutionNote,
      }),
    },
  )
}

export async function fetchChatReports(limit = 20) {
  return gatewayJson<{ reports?: RiskReport[] }>(
    `/v1/chat/reports${queryString({ limit })}`,
    { includeAuth: true },
  )
}
