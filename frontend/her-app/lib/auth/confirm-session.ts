import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { clearSessionAndRedirectToWelcome, getAccessToken } from '@/lib/auth/session'

/**
 * Some background requests may transiently return 401 even when the login session
 * is still usable. Re-check /auth/me before clearing the whole session.
 */
export async function confirmSessionOrRedirectToWelcome(): Promise<boolean> {
  if (!getAccessToken()) {
    clearSessionAndRedirectToWelcome()
    return false
  }

  const authMe = await hydrateSessionFromAuthMe()
  if (authMe) {
    return true
  }

  clearSessionAndRedirectToWelcome()
  return false
}
