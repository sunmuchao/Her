import { useQuery } from '@tanstack/react-query'
import { fetchCollectedStatements } from '@/lib/api/endpoints/collected'
import { getProfileId } from '@/lib/auth/session'
import { queryKeys } from '@/lib/query-keys'

export type CollectedStatementsData = {
  collected_statements?: Record<string, unknown>
  collected_items?: Record<string, {
    value: unknown
    source_channel?: string
    collected_at?: string
    evidence?: string
    source_type?: string
  }>
}

export function useCollectedStatements() {
  return useQuery({
    queryKey: queryKeys.collectedStatements,
    queryFn: async (): Promise<CollectedStatementsData> => {
      // ✅ 修复：先获取profileId，再传给fetchCollectedStatements（防止使用默认值）
      const profileId = getProfileId()
      if (!profileId) {
        // 如果没有profileId，返回空对象（防止403错误）
        return { collected_statements: {}, collected_items: {} }
      }
      return fetchCollectedStatements(profileId)
    },
    staleTime: 60 * 1000, // 1 分钟内不重新获取
  })
}