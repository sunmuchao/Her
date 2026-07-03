'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchOpsAsyncJobDashboard, fetchOpsTaskDetail, fetchOpsWorkbenchSummary } from '@/lib/api/endpoints/ops'
import { fetchConversionViewsForSubscription } from '@/lib/api/endpoints/recommendation'
import {
  fetchChatReports,
  fetchFraudNetworks,
  fetchRiskAppeals,
  fetchRiskCases,
  fetchRiskDashboard,
} from '@/lib/api/endpoints/risk-ops'
import { queryKeys } from '@/lib/query-keys'
import type { GatewayRequestInit } from '@/lib/api/client'

/**
 * Ops Workbench Summary React Query Hook
 *
 * 使用 React Query 管理 ops workbench 数据获取，提供：
 * - 自动缓存和重新验证
 * - 智能轮询（页面可见时才轮询）
 * - 请求取消支持
 * - 窗口聚焦时刷新
 *
 * @param options - 配置选项
 * @param options.enabled - 是否启用查询（默认 true）
 * @param options.refetchInterval - 轮询间隔（毫秒），默认 false 不轮询
 * @param options.limit - 请求数据限制（默认 5）
 *
 * @returns React Query 结果对象
 *
 * @example
 * ```typescript
 * const {
 *   data: summary,      // OpsWorkbenchSummary 数据
 *   error: loadError,   // 错误信息
 *   isLoading: loading, // 是否正在加载
 *   refetch: loadSummary, // 手动刷新函数
 * } = useOpsWorkbenchSummary({
 *   enabled: autoRefreshEnabled && activeTab === 'ops' && isVisible,
 *   refetchInterval: autoRefreshEnabled && isVisible ? 30000 : false,
 * })
 * ```
 */
export function useOpsWorkbenchSummary(options?: {
  enabled?: boolean
  refetchInterval?: number | false
  limit?: number
}) {
  const {
    enabled = true,
    refetchInterval = false,
    limit = 5,
  } = options || {}

  return useQuery({
    queryKey: queryKeys.opsWorkbenchSummary,
    queryFn: ({ signal }) =>
      fetchOpsWorkbenchSummary(limit, {
        signal,
        includeAuth: true,
      } as GatewayRequestInit),
    staleTime: 30 * 1000, // 30秒内数据视为新鲜
    gcTime: 5 * 60 * 1000, // 缓存保留5分钟
    refetchOnWindowFocus: true, // 窗口聚焦时刷新
    enabled,
    refetchInterval, // 智能轮询（页面不可见时自动暂停）
    retry: 1, // 失败重试1次
  })
}

export function useOpsAsyncJobDashboard(options?: {
  enabled?: boolean
  refetchInterval?: number | false
  limit?: number
}) {
  const {
    enabled = true,
    refetchInterval = false,
    limit = 5,
  } = options || {}

  return useQuery({
    queryKey: queryKeys.opsAsyncJobDashboard(limit),
    queryFn: ({ signal }) =>
      fetchOpsAsyncJobDashboard(limit, {
        signal,
        includeAuth: true,
      } as GatewayRequestInit),
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
    enabled,
    refetchInterval,
    retry: 1,
  })
}

export function useOpsTaskDetail(pollPath: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.opsTaskDetail(pollPath || 'none'),
    queryFn: ({ signal }) =>
      fetchOpsTaskDetail(String(pollPath), {
        signal,
        includeAuth: true,
      } as GatewayRequestInit),
    enabled: Boolean(pollPath) && enabled,
    staleTime: 10 * 1000,
    retry: 1,
  })
}

export function useRiskDashboard(days = 7, enabled = true) {
  return useQuery({
    queryKey: queryKeys.riskDashboard(days),
    queryFn: () => fetchRiskDashboard(days),
    enabled,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useRiskCases(limit = 20, enabled = true) {
  return useQuery({
    queryKey: queryKeys.riskCases(limit),
    queryFn: () => fetchRiskCases(limit),
    enabled,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useRiskReports(limit = 20, enabled = true) {
  return useQuery({
    queryKey: queryKeys.riskReports(limit),
    queryFn: () => fetchChatReports(limit),
    enabled,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useFraudNetworks(limit = 20, enabled = true) {
  return useQuery({
    queryKey: queryKeys.fraudNetworks(limit),
    queryFn: () => fetchFraudNetworks(limit),
    enabled,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useRiskAppeals(limit = 20, enabled = true) {
  return useQuery({
    queryKey: queryKeys.riskAppeals(limit),
    queryFn: () => fetchRiskAppeals(limit),
    enabled,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useConversionViews(subscriptionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.conversionViews(subscriptionId),
    queryFn: () => fetchConversionViewsForSubscription(subscriptionId),
    enabled: enabled && Boolean(subscriptionId),
    staleTime: 30 * 1000,
    retry: 1,
  })
}
