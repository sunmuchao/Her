import { fetchAuthMe } from '@/lib/auth/auth-api'
import type { OnboardingGatePayload } from '@/lib/auth/onboarding-gate'
import { applyAuthMePayload, getAccessToken } from '@/lib/auth/session'

export type AuthMePayload = OnboardingGatePayload & {
  user?: OnboardingGatePayload['user'] & {
    phone?: string
    display_name?: string
    avatar_url?: string
    case_id?: string
    onboarding_status?: string  // ✅ 新增：检测onboarding状态
  }
  profile?: Record<string, unknown>
  session?: Record<string, unknown>
  identity_vocabulary?: Array<{ field: string; scope: string; meaning: string }>
}

/** Load requester/profile IDs from /v1/auth/me after login (never env defaults). */
export async function hydrateSessionFromAuthMe(): Promise<AuthMePayload | null> {
  if (!getAccessToken()) return null
  try {
    const data = (await fetchAuthMe()) as AuthMePayload
    applyAuthMePayload(data)

    // ✅ 新增：检测用户未完成onboarding，抛出错误提示用户需要先完成资料填写
    const onboardingStatus = data.user?.onboarding_status || data.onboarding?.onboarding_status
    if (onboardingStatus === 'not_started') {
      console.warn('[hydrate] 用户未完成资料填写，onboarding_status = not_started')
      // 返回数据，让前端判断是否需要跳转到onboarding页面
    }

    return data
  } catch {
    return null
  }
}
