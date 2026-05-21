import { fetchAuthMe } from '@/lib/auth/auth-api'
import { applyAuthMePayload, getAccessToken } from '@/lib/auth/session'

/** Load requester/profile IDs from /v1/auth/me after login (never env defaults). */
export async function hydrateSessionFromAuthMe(): Promise<boolean> {
  if (!getAccessToken()) return false
  try {
    const data = await fetchAuthMe()
    applyAuthMePayload(data)
    const user = data.user || {}
    return user.requester_id != null || user.profile_id != null
  } catch {
    return false
  }
}
