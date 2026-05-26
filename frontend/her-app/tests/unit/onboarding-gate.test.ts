import { describe, expect, it } from 'vitest'
import { isOnboardingComplete, resolvePostLoginPage } from '@/lib/auth/onboarding-gate'
import type { LoginPayload } from '@/lib/auth/session'

describe('onboarding-gate', () => {
  it('treats completed onboarding_status as done', () => {
    expect(isOnboardingComplete({ user: { onboarding_status: 'completed' } })).toBe(true)
  })

  it('treats linked profile_id as done', () => {
    expect(isOnboardingComplete({ user: { profile_id: 10001 } })).toBe(true)
  })

  it('treats missing profile as incomplete', () => {
    expect(
      isOnboardingComplete({
        user: { onboarding_status: 'not_started' },
      }),
    ).toBe(false)
  })

  it('sends new users to welcome page when onboarding is incomplete', () => {
    const payload: LoginPayload = {
      user: { is_new_user: true, onboarding_status: 'not_started' },
      flow: { next_path: '/onboarding' },
    }
    expect(resolvePostLoginPage(payload)).toBe('auth-new-user-welcome')
  })

  it('sends returning users without profile to onboarding page', () => {
    const payload: LoginPayload = {
      user: { is_new_user: false, onboarding_status: 'not_started' },
      flow: { next_path: '' },
    }
    expect(resolvePostLoginPage(payload)).toBe('auth-onboarding')
  })

  it('sends completed users to discover', () => {
    const payload: LoginPayload = {
      user: { is_new_user: false, onboarding_status: 'completed', profile_id: 10001 },
    }
    expect(resolvePostLoginPage(payload)).toBe('main-matchmaker')
  })

  it('prefers auth/me profile linkage for returning users', () => {
    const payload: LoginPayload = {
      user: { is_new_user: false, onboarding_status: 'not_started' },
    }
    expect(
      resolvePostLoginPage(payload, {
        user: { onboarding_status: 'completed', profile_id: 10001 },
      }),
    ).toBe('main-matchmaker')
  })

  it('routes wechat users without phone to binding page', () => {
    const payload: LoginPayload = {
      user: { phone_bound: false },
      flow: { next_path: '/bind-phone' },
    }
    expect(resolvePostLoginPage(payload)).toBe('auth-wechat-binding')
  })
})
