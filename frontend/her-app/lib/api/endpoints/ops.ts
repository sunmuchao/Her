import { gatewayJson } from '@/lib/api/client'
import type { GatewayRequestInit } from '@/lib/api/client'

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

export async function fetchOpsWorkbenchSummary(limit = 5, init?: GatewayRequestInit) {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : ''
  return gatewayJson<OpsWorkbenchSummary>(`/v1/ops/workbench/summary${query}`, {
    includeAuth: true,
    signal: init?.signal, // 支持请求取消
  })
}

export async function fetchOpsAsyncJobDashboard(limit = 5, init?: GatewayRequestInit) {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : ''
  return gatewayJson<OpsWorkbenchSummary>(`/v1/ops/async-jobs/dashboard${query}`, {
    includeAuth: true,
    signal: init?.signal,
  })
}

export async function fetchOpsTaskDetail(pollPath: string, init?: GatewayRequestInit) {
  return gatewayJson<{ job?: Record<string, unknown>; trace_id?: string }>(pollPath, {
    includeAuth: true,
    signal: init?.signal,
  })
}
