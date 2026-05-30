'use client'

import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { fetchTrustHub } from '@/lib/api/endpoints/trust-hub'
import { fetchRelationshipsUnreadSummary } from '@/lib/api/endpoints/chat'
import { getUserId, getProfileId } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'

/**
 * Relationships 页面聚合数据 Hook
 *
 * 聚合多个数据源（牵线 Cases、TrustHub、未读统计），
 * 统一管理加载状态和错误状态
 *
 * 对应 ProfilePage 的 useProfilePageData 模式
 */
export function useRelationshipsPageData() {
  const userId = getUserId()
  const profileId = getProfileId()

  // 牵线 cases 查询
  const casesQuery = useQuery({
    queryKey: ['relationships', 'cases', userId],
    queryFn: () => fetchMyProxyIntroCases(),
    staleTime: 30000, // 30 秒内不重新请求
    enabled: !!userId,
  })

  // TrustHub 查询（用于获取待处理认证项）
  const trustQuery = useQuery({
    queryKey: ['trust-hub', userId, profileId],
    queryFn: () => fetchTrustHub({ userId: userId!, profileId }),
    staleTime: 60000, // 60 秒内不重新请求
    enabled: !!userId,
  })

  // 未读统计查询
  const unreadQuery = useQuery({
    queryKey: ['relationships', 'unread-summary', userId],
    queryFn: () => fetchRelationshipsUnreadSummary(),
    staleTime: 20000, // 20 秒内不重新请求
    enabled: !!userId,
  })

  // 计算整体加载状态
  const isLoading = useMemo(() => {
    return casesQuery.isLoading || unreadQuery.isLoading
  }, [casesQuery.isLoading, unreadQuery.isLoading])

  // 计算整体错误状态
  const error = useMemo(() => {
    if (casesQuery.error) {
      return getErrorMessage(casesQuery.error, '牵线记录加载失败')
    }
    if (unreadQuery.error) {
      return '未读统计加载失败'
    }
    return null
  }, [casesQuery.error, unreadQuery.error])

  // 是否正在刷新（已加载但正在后台刷新）
  const isRefreshing = useMemo(() => {
    return (
      !isLoading &&
      (casesQuery.isFetching || unreadQuery.isFetching || trustQuery.isFetching)
    )
  }, [isLoading, casesQuery.isFetching, unreadQuery.isFetching, trustQuery.isFetching])

  return {
    // 各数据源的原始数据
    cases: casesQuery.data?.cases || [],
    trustHub: trustQuery.data,
    unreadSummary: unreadQuery.data,

    // 状态
    isLoading,
    isRefreshing,
    error,

    // refetch 方法（用于手动刷新）
    refetch: async () => {
      await Promise.all([
        casesQuery.refetch(),
        trustQuery.refetch(),
        unreadQuery.refetch(),
      ])
    },

    // 原始 query 对象（用于高级用法）
    queries: {
      cases: casesQuery,
      trust: trustQuery,
      unread: unreadQuery,
    },
  }
}