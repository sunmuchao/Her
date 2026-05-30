'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchAuthMe } from '@/lib/auth/auth-api'
import { queryKeys } from '@/lib/query-keys'
import { ensureDevAuthSession } from '@/lib/auth/dev-bootstrap'
import { getAccessToken } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { isAuthStubEnabled } from '@/lib/env'
import { DEMO_PROFILE } from '@/lib/fixtures/demo-profiles'

export type AuthMeData = {
  user?: {
    user_id?: string
    phone?: string
    display_name?: string
    avatar_url?: string
    profile_id?: number
    requester_id?: number
    case_id?: string
    onboarding_status?: string
  }
  onboarding?: {
    profile_id?: number
    basic_info?: Record<string, unknown>
    preference?: Record<string, unknown>
  }
  profile?: Record<string, unknown>
  principal?: {
    user_id?: string
    profile_id?: number
    requester_id?: number
    user_key?: string
    roles?: string[]
    auth_source?: string
  }
  identity_vocabulary?: Array<{ field: string; scope: string; meaning: string }>
}

export function useAuthMe() {
  return useQuery({
    queryKey: queryKeys.authMe,
    queryFn: async (): Promise<AuthMeData> => {
      let token = getAccessToken()
      if (!token && isAuthStubEnabled()) {
        const ok = await ensureDevAuthSession()
        token = ok ? getAccessToken() : null
      }

      if (!token) {
        if (canUseMockFallback()) {
          return {
            user: {
              user_id: 'demo-user',
              requester_id: 1,
              profile_id: 1,
              display_name: DEMO_PROFILE.name,
              avatar_url: DEMO_PROFILE.avatar,
            },
          }
        }
        throw new Error('请先登录后查看个人资料')
      }

      return fetchAuthMe()
    },
    staleTime: 2 * 60 * 1000, // 2 分钟内不重新获取
  })
}