import { gatewayJson } from '@/lib/api/client'
import { getDeviceId } from '@/lib/auth/device-id'
import type { LoginPayload } from '@/lib/auth/session'
import { isAuthStubEnabled } from '@/lib/env'

export type SmsSendCodeResponse = {
  challenge_id?: string
  flow?: { next_path?: string }
}

export type OneTapCreateResponse = {
  attempt_id?: string
  masked_phone?: string
  provider_payload?: { operator_token?: string }
}

function wechatCode(): string {
  return isAuthStubEnabled() ? 'wx-code-1' : ''
}

function oneTapToken(fallback?: string): string {
  if (fallback) return fallback
  return isAuthStubEnabled() ? 'carrier-token-1' : ''
}

export async function sendSmsCode(params: {
  phone: string
  scene: 'login' | 'bind_phone'
}) {
  return gatewayJson<SmsSendCodeResponse>('/v1/auth/sms/send-code', {
    method: 'POST',
    includeAuth: params.scene === 'bind_phone',
    body: JSON.stringify({
      phone: params.phone,
      scene: params.scene,
      device_id: getDeviceId(),
    }),
  })
}

export async function verifySmsCode(params: {
  phone: string
  code: string
  challengeId?: string | null
}) {
  return gatewayJson<LoginPayload>('/v1/auth/sms/verify-code', {
    method: 'POST',
    includeAuth: false,
    body: JSON.stringify({
      phone: params.phone,
      code: params.code,
      challenge_id: params.challengeId,
      device_id: getDeviceId(),
    }),
  })
}

export async function bindPhoneWithSms(params: {
  phone: string
  code: string
  challengeId?: string | null
}) {
  return gatewayJson<{ ok?: boolean }>('/v1/auth/wechat/bind-phone', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      phone: params.phone,
      code: params.code,
      challenge_id: params.challengeId,
      device_id: getDeviceId(),
    }),
  })
}

export async function wechatLogin() {
  const code = wechatCode()
  if (!code && !isAuthStubEnabled()) {
    throw new Error('微信登录尚未接入，请在开发环境开启 NEXT_PUBLIC_USE_AUTH_STUB')
  }
  return gatewayJson<LoginPayload>('/v1/auth/wechat/login', {
    method: 'POST',
    includeAuth: false,
    body: JSON.stringify({
      code: code || 'wx-code-1',
      device_id: getDeviceId(),
      client_type: 'web',
    }),
  })
}

export async function createOneTapAttempt() {
  return gatewayJson<OneTapCreateResponse>('/v1/auth/one-tap/create', {
    method: 'POST',
    includeAuth: false,
    body: JSON.stringify({
      device_id: getDeviceId(),
      client_type: 'web',
    }),
  })
}

export async function verifyOneTap(params: {
  attemptId: string
  operatorToken?: string
}) {
  return gatewayJson<LoginPayload>('/v1/auth/one-tap/verify', {
    method: 'POST',
    includeAuth: false,
    body: JSON.stringify({
      attempt_id: params.attemptId,
      operator_token: oneTapToken(params.operatorToken),
      device_id: getDeviceId(),
      client_type: 'web',
    }),
  })
}

export type OnboardingPayload = {
  basic_info?: {
    name?: string
    birthday?: string
    gender?: string
    sexual_orientation?: string
    location?: string
    city?: string
    relationship_goal?: string
    marriage_status?: string
    has_children?: string
    profile_id?: number
  }
  preference?: {
    relationship_goal?: string
    tags?: string[]
    age_range?: [number, number]
    location_pref?: string
  }
  photos?: string[]
  mark_completed?: boolean
}

export async function fetchAuthMe() {
  return gatewayJson<{
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
  }>('/v1/auth/me', {
    method: 'GET',
    includeAuth: true,
  })
}

export async function submitOnboarding(payload: OnboardingPayload) {
  return gatewayJson<{
    ok?: boolean
    profile_id?: number
    requester_id?: number
    user?: { user_id?: string; onboarding_status?: string }
    onboarding?: {
      basic_info?: Record<string, unknown>
      preference?: Record<string, unknown>
    }
  }>('/v1/auth/onboarding', {
    method: 'PATCH',
    includeAuth: true,
    body: JSON.stringify(payload),
  })
}
