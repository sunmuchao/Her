import type { AppPage } from '@/lib/navigation/types'
import type { LoginPayload } from '@/lib/auth/session'

export type OnboardingGatePayload = {
  user?: {
    is_new_user?: boolean
    phone_bound?: boolean
    onboarding_status?: string
    profile_id?: number
    requester_id?: number
  }
  onboarding?: {
    onboarding_status?: string
    profile_id?: number
  }
  principal?: {
    profile_id?: number
    requester_id?: number
  }
  flow?: { next_path?: string }
}

export function isOnboardingComplete(data: OnboardingGatePayload): boolean {
  const status = data.user?.onboarding_status ?? data.onboarding?.onboarding_status
  if (status === 'completed') return true

  const profileId =
    data.user?.profile_id ??
    data.onboarding?.profile_id ??
    data.principal?.profile_id ??
    data.user?.requester_id ??
    data.principal?.requester_id

  return profileId != null && profileId > 0
}

export function resolvePostLoginPage(
  payload: LoginPayload,
  authMe?: OnboardingGatePayload | null,
): AppPage {
  if (payload.flow?.next_path === '/bind-phone' || payload.user?.phone_bound === false) {
    return 'auth-wechat-binding'
  }

  const merged: OnboardingGatePayload = {
    user: { ...payload.user, ...authMe?.user },
    onboarding: authMe?.onboarding ?? payload.onboarding,
    principal: authMe?.principal,
    flow: payload.flow,
  }

  if (isOnboardingComplete(merged)) {
    return 'main-matchmaker'
  }

  if (payload.user?.is_new_user || payload.flow?.next_path === '/onboarding') {
    return 'auth-new-user-welcome'
  }

  return 'auth-onboarding'
}
