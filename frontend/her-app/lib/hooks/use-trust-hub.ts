'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchTrustHub } from '@/lib/api/endpoints/trust-hub'
import { getUserId, getProfileId } from '@/lib/auth/session'
import { queryKeys } from '@/lib/query-keys'

export type TrustHubData = {
  trust_hub: {
    summary?: {
      pending_verification_count?: number
      pending_appeal_count?: number
      active_risk_count?: number
      notification_count?: number
    }
    verification_center?: {
      items?: Array<{
        id?: string
        name?: string
        status?: string
        description?: string
        type?: string
      }>
    }
    risk_records?: {
      items?: Array<{
        title?: string
        description?: string
        status?: string
        time?: string
      }>
    }
    notifications?: Array<{
      title?: string
      body?: string
      type?: string
      created_at?: string
    }>
  }
}

export function useTrustHub() {
  const userId = getUserId()
  const profileId = getProfileId()

  return useQuery({
    queryKey: userId ? queryKeys.trustHub(userId, profileId) : ['trust', 'hub', 'no-user'],
    queryFn: async (): Promise<TrustHubData> => {
      if (!userId) {
        throw new Error('请先登录后再查看信任中心')
      }

      return fetchTrustHub({ userId, profileId })
    },
    enabled: Boolean(userId), // 只有有 userId 时才执行
    staleTime: 60 * 1000, // 1 分钟内不重新获取
  })
}