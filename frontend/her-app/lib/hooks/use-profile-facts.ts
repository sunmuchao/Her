'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchProfileFacts } from '@/lib/api/endpoints/collected'
import { queryKeys } from '@/lib/query-keys'

export type ProfileFactsData = {
  profile_facts?: Record<string, unknown>
  photos?: string[]
}

export function useProfileFacts() {
  return useQuery({
    queryKey: queryKeys.profileFacts,
    queryFn: async (): Promise<ProfileFactsData> => {
      return fetchProfileFacts()
    },
    staleTime: 60 * 1000, // 1 分钟内不重新获取
  })
}
