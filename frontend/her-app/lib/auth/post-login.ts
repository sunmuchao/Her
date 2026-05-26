import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { applyLoginPayload, type LoginPayload } from '@/lib/auth/session'
import { resolvePostLoginPage } from '@/lib/auth/onboarding-gate'
import type { AppPage } from '@/lib/navigation/types'

export async function navigateAfterLogin(
  payload: LoginPayload,
  onNavigate: (page: AppPage) => void,
): Promise<AppPage> {
  applyLoginPayload(payload)
  const authMe = await hydrateSessionFromAuthMe()
  const page = resolvePostLoginPage(payload, authMe)
  onNavigate(page)
  return page
}

/** Use after actions that mutate auth state without a full login payload (e.g. bind phone). */
export async function navigateAfterAuthSession(
  onNavigate: (page: AppPage) => void,
  payload: LoginPayload = {},
): Promise<AppPage> {
  const authMe = await hydrateSessionFromAuthMe()
  const page = resolvePostLoginPage(payload, authMe)
  onNavigate(page)
  return page
}
