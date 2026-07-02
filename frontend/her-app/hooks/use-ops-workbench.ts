'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchOpsWorkbenchSummary } from '@/lib/api/endpoints/ops'
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