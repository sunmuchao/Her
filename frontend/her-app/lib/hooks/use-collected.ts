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
  const profileId = getProfileId()

  return useQuery({
    queryKey: queryKeys.collectedStatements(profileId),
    enabled: Boolean(profileId),
    queryFn: async (): Promise<CollectedStatementsData> => {
      if (!profileId) {
        throw new Error('profileId is required')
      }
      return fetchCollectedStatements(profileId)
    },
    staleTime: 60 * 1000, // 1 分钟内不重新获取
  })
}
