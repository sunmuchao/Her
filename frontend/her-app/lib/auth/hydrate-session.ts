import { fetchAuthMe } from '@/lib/auth/auth-api'
import type { OnboardingGatePayload } from '@/lib/auth/onboarding-gate'
import { applyAuthMePayload, getAccessToken } from '@/lib/auth/session'

export type AuthMePayload = OnboardingGatePayload & {
  user?: OnboardingGatePayload['user'] & {
    phone?: string
    display_name?: string
    avatar_url?: string
    case_id?: string
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
    return data
  } catch {
    return null
  }
}
