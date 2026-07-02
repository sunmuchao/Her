'use client'

import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-keys'

/**
 * 认证缓存失效工具 Hook
 *
 * 提供统一的认证相关缓存失效方法，用于：
 * - 提交认证材料成功后
 * - 认证审核通过/失败后
 * - 认证状态变化时
 */
export function useVerificationCacheInvalidation() {
  const queryClient = useQueryClient()

  /**
   * 失效所有认证相关的缓存
   *
   * 包括：
   * - verificationSubmissions: 认证提交记录
   * - verificationNotifications: 认证通知
   * - fieldVerifications: 字段认证状态
   * - trustHub: 信任中心（认证进度）
   * - authMe: 用户信息（认证状态）
   * - profileFacts: 用户资料（认证状态）
   */
  const invalidateAllVerificationCache = async () => {
    console.log('[Cache Invalidation] 开始失效认证相关缓存')

    await Promise.all([
      // 失效认证提交记录
      queryClient.invalidateQueries({
        queryKey: queryKeys.verificationSubmissions,
      }),
      // 失效认证通知
      queryClient.invalidateQueries({
        queryKey: queryKeys.verificationNotifications,
      }),
      // 失效字段认证状态
      queryClient.invalidateQueries({
        queryKey: queryKeys.fieldVerifications,
      }),
      // 失效信任中心数据（包含认证进度）
      queryClient.invalidateQueries({
        queryKey: ['trust', 'hub'],
      }),
      // 失效用户认证信息
      queryClient.invalidateQueries({
        queryKey: queryKeys.authMe,
      }),
      // 失效用户资料（包含认证状态）
      queryClient.invalidateQueries({
        queryKey: queryKeys.profileFacts,
      }),
    ])

    console.log('[Cache Invalidation] 认证相关缓存已失效')
  }

  return {
    invalidateAllVerificationCache,
  }
}