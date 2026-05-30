'use client'

import { useAuthMe, type AuthMeData } from '@/lib/hooks/use-auth-me'
import { useProfileFacts, type ProfileFactsData } from '@/lib/hooks/use-profile-facts'
import {
  useCollectedStatements,
  type CollectedStatementsData,
} from '@/lib/hooks/use-collected'
import { useTrustHub, type TrustHubData } from '@/lib/hooks/use-trust-hub'
import { useMemo } from 'react'

/**
 * Profile 页面聚合数据 Hook
 *
 * 聚合多个数据源（Auth、Facts、Collected、TrustHub），
 * 统一管理加载状态和错误状态
 */
export function useProfilePageData() {
  const authQuery = useAuthMe()
  const factsQuery = useProfileFacts()
  const collectedQuery = useCollectedStatements()
  const trustQuery = useTrustHub()

  // 计算整体加载状态
  // 所有必需数据加载完成才算完成
  const isLoading = useMemo(() => {
    return authQuery.isLoading || factsQuery.isLoading || collectedQuery.isLoading
  }, [authQuery.isLoading, factsQuery.isLoading, collectedQuery.isLoading])

  // 计算整体错误状态
  // 任一必需数据出错就算出错
  const error = useMemo(() => {
    if (authQuery.error) {
      return authQuery.error instanceof Error
        ? authQuery.error.message
        : '用户信息加载失败'
    }
    if (factsQuery.error) {
      return factsQuery.error instanceof Error
        ? factsQuery.error.message
        : '资料加载失败'
    }
    if (collectedQuery.error) {
      return collectedQuery.error instanceof Error
        ? collectedQuery.error.message
        : '偏好加载失败'
    }
    return null
  }, [authQuery.error, factsQuery.error, collectedQuery.error])

  // 是否正在刷新（已加载但正在后台刷新）
  const isRefreshing = useMemo(() => {
    return (
      !isLoading &&
      (authQuery.isFetching || factsQuery.isFetching || collectedQuery.isFetching)
    )
  }, [isLoading, authQuery.isFetching, factsQuery.isFetching, collectedQuery.isFetching])

  return {
    // 各数据源的原始数据
    auth: authQuery.data,
    facts: factsQuery.data,
    collected: collectedQuery.data,
    trust: trustQuery.data,

    // 状态
    isLoading,
    isRefreshing,
    error,

    // refetch 方法（用于手动刷新）
    refetch: async () => {
      await Promise.all([
        authQuery.refetch(),
        factsQuery.refetch(),
        collectedQuery.refetch(),
        trustQuery.refetch(),
      ])
    },

    // 原始 query 对象（用于高级用法）
    queries: {
      auth: authQuery,
      facts: factsQuery,
      collected: collectedQuery,
      trust: trustQuery,
    },
  }
}

/**
 * Profile 页面数据类型
 */
export type ProfilePageData = ReturnType<typeof useProfilePageData>