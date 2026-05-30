'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchCollectedStatements } from '@/lib/api/endpoints/collected'
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
      return fetchCollectedStatements()
    },
    staleTime: 60 * 1000, // 1 分钟内不重新获取
  })
}