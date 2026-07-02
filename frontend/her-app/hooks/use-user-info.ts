'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchUserInfo } from '@/lib/api/endpoints/user-info'
import type { VerificationSubmissionDetail } from '@/lib/api/endpoints/field-verification'
import { queryKeys } from '@/lib/query-keys'

/**
 * 用户信息缓存 React Query Hook
 *
 * 用于缓存用户基本信息，避免同一用户审核多个字段时重复请求。
 *
 * @param profileId - 用户档案ID
 * @returns React Query 结果对象
 *
 * @example
 * ```typescript
 * const {
 *   data: userInfo,      // 用户信息
 *   isLoading: loadingUserInfo, // 是否正在加载
 * } = useUserInfo(submission.profile_id)
 * ```
 */
export function useUserInfo(submission: Pick<VerificationSubmissionDetail, 'profile_id' | 'source_dsn' | 'source_table_name'>) {
  return useQuery({
    queryKey: queryKeys.userInfo(submission.profile_id, submission.source_dsn, submission.source_table_name),
    queryFn: ({ signal }) => fetchUserInfo(submission.profile_id, signal, {
      sourceDsn: submission.source_dsn,
      sourceTableName: submission.source_table_name,
    }),
    staleTime: 5 * 60 * 1000, // 5分钟内数据视为新鲜
    gcTime: 10 * 60 * 1000, // 缓存保留10分钟
    enabled: submission.profile_id > 0, // 仅在有有效 profileId 时启用
    retry: 1, // 失败重试1次
  })
}
