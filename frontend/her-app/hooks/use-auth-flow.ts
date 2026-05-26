'use client'

import { useCallback, useState } from 'react'
import { flushSync } from 'react-dom'
import {
  bindPhoneWithSms,
  createOneTapAttempt,
  sendSmsCode,
  verifyOneTap,
  verifySmsCode,
  wechatLogin,
} from '@/lib/auth/auth-api'
import { navigateAfterAuthSession, navigateAfterLogin } from '@/lib/auth/post-login'
import { clearSession, type LoginPayload } from '@/lib/auth/session'
import type { AppPage } from '@/lib/navigation/types'
import { getErrorMessage } from '@/lib/api/errors'

export type AuthMode = 'sms-login' | 'wechat-bind'

const PENDING_PHONE_KEY = 'her_pending_auth_phone'
const PENDING_ONE_TAP_KEY = 'her_pending_one_tap_attempt'

function readPendingPhone(): string {
  if (typeof window === 'undefined') return ''
  return window.sessionStorage.getItem(PENDING_PHONE_KEY) || ''
}

function readPendingOneTap(): {
  attemptId: string
  maskedPhone: string
  operatorToken?: string
} | null {
  if (typeof window === 'undefined') return null
  const raw = window.sessionStorage.getItem(PENDING_ONE_TAP_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as {
      attemptId: string
      maskedPhone: string
      operatorToken?: string
    }
  } catch {
    return null
  }
}

export function useAuthFlow(onNavigate: (page: AppPage) => void) {
  const [authPhone, setAuthPhone] = useState(() => readPendingPhone())
  const [authMode, setAuthMode] = useState<AuthMode>('sms-login')
  const [smsChallengeId, setSmsChallengeId] = useState<string | null>(null)
  const [oneTapAttempt, setOneTapAttempt] = useState<{
    attemptId: string
    maskedPhone: string
    operatorToken?: string
  } | null>(() => readPendingOneTap())
  const [wechatProfile, setWechatProfile] = useState<{
    nickname?: string
    avatar_url?: string
  } | null>(null)

  const completeLoginFlow = useCallback(
    async (payload: LoginPayload) => {
      if (payload.wechat_profile) {
        setWechatProfile(payload.wechat_profile)
      }
      const page = await navigateAfterLogin(payload, onNavigate)
      if (page === 'auth-wechat-binding') {
        setAuthMode('wechat-bind')
      }
    },
    [onNavigate],
  )

  const resetAuthOnWelcome = useCallback(() => {
    clearSession()
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(PENDING_PHONE_KEY)
      window.sessionStorage.removeItem(PENDING_ONE_TAP_KEY)
    }
  }, [])

  const requestSmsCode = useCallback(
    async (phone: string) => {
      const data = await sendSmsCode({
        phone,
        scene: authMode === 'wechat-bind' ? 'bind_phone' : 'login',
      })
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(PENDING_PHONE_KEY, phone)
      }
      flushSync(() => {
        setAuthPhone(phone)
        setSmsChallengeId(data.challenge_id || null)
      })
      onNavigate('auth-verification-code')
    },
    [authMode, onNavigate],
  )

  const verifySms = useCallback(
    async (code: string) => {
      if (authMode === 'wechat-bind') {
        const data = await bindPhoneWithSms({
          phone: authPhone,
          code,
          challengeId: smsChallengeId,
        })
        if (data.ok) {
          await navigateAfterAuthSession(onNavigate)
        }
        return
      }
      const phone = authPhone || readPendingPhone()
      const data = await verifySmsCode({
        phone,
        code,
        challengeId: smsChallengeId,
      })
      await completeLoginFlow(data)
    },
    [authMode, authPhone, smsChallengeId, completeLoginFlow, onNavigate],
  )

  const resendSmsCode = useCallback(async () => {
    await requestSmsCode(authPhone)
  }, [authPhone, requestSmsCode])

  const startWechatLogin = useCallback(async () => {
    const data = await wechatLogin()
    await completeLoginFlow(data)
  }, [completeLoginFlow])

  const startOneTapLogin = useCallback(async () => {
    const data = await createOneTapAttempt()
    const attempt = {
      attemptId: data.attempt_id || '',
      maskedPhone: data.masked_phone || '138****8000',
      operatorToken: data.provider_payload?.operator_token,
    }
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(PENDING_ONE_TAP_KEY, JSON.stringify(attempt))
    }
    flushSync(() => setOneTapAttempt(attempt))
    onNavigate('auth-one-click')
  }, [onNavigate])

  const verifyOneTapLogin = useCallback(async () => {
    const attempt = oneTapAttempt || readPendingOneTap()
    if (!attempt?.attemptId) {
      throw new Error('一键登录会话不存在，请返回重试')
    }
    const data = await verifyOneTap({
      attemptId: attempt.attemptId,
      operatorToken: attempt.operatorToken,
    })
    await completeLoginFlow(data)
  }, [oneTapAttempt, completeLoginFlow])

  return {
    authPhone,
    authMode,
    setAuthMode,
    smsChallengeId,
    oneTapAttempt,
    wechatProfile,
    resetAuthOnWelcome,
    requestSmsCode,
    verifySms,
    resendSmsCode,
    startWechatLogin,
    startOneTapLogin,
    verifyOneTapLogin,
    getErrorMessage,
  }
}
