import { gatewayJson } from '@/lib/api/client'

export type OpsWorkbenchSummary = {
  dashboard?: {
    systems?: Record<
      string,
      {
        summary?: Record<string, number>
        recent_jobs?: Array<Record<string, unknown>>
      }
    >
    ledger?: { available?: boolean; dashboard?: Record<string, unknown> }
    funnel?: Record<string, unknown>
    totals?: Record<string, number>
  }
  relations_preview?: Array<Record<string, unknown>>
  ops_actions?: { recommendation?: string[] }
  override_api?: string
  principal?: Record<string, unknown>
}

export async function fetchOpsWorkbenchSummary(limit = 5) {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : ''
  return gatewayJson<OpsWorkbenchSummary>(`/v1/ops/workbench/summary${query}`, {
    includeAuth: true,
  })
}
