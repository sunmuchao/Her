import { applyAuthPrincipalPayload } from '@/lib/auth/principal'
import {
  getDefaultCaseId,
  getDefaultProfileId,
  getDefaultRequesterId,
  getDefaultUserId,
} from '@/lib/env'
import { clearServerSession, persistServerSession } from '@/lib/auth/server-session'

const ACCESS_TOKEN_KEY = 'her_demo_access_token'
const SESSION_CONTEXT_KEY = 'her_session_context'

export type SessionContext = {
  accessToken?: string
  userId?: string
  requesterId?: number
  profileId?: number
  caseId?: string
  /** True when login/onboarding linked a real profile (not env defaults). */
  profileLinked?: boolean
  /** User's own avatar URL */
  avatarUrl?: string
}

export type LoginPayload = {
  session?: { access_token?: string; refresh_token?: string }
  user?: {
    user_id?: string
    is_new_user?: boolean
    phone_bound?: boolean
    requester_id?: number
    profile_id?: number
    case_id?: string
    onboarding_status?: string
  }
  onboarding?: { profile_id?: number }
  flow?: { next_path?: string; scenario?: string }
  wechat_profile?: { nickname?: string; avatar_url?: string }
}

function readStoredContext(): SessionContext {
  if (typeof window === 'undefined') {
    return {}
  }
  const raw = window.localStorage.getItem(SESSION_CONTEXT_KEY)
  if (!raw) {
    return {}
  }
  try {
    return JSON.parse(raw) as SessionContext
  } catch {
    return {}
  }
}

function writeContext(ctx: SessionContext) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SESSION_CONTEXT_KEY, JSON.stringify(ctx))
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function clearSession() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(ACCESS_TOKEN_KEY)
  window.localStorage.removeItem(SESSION_CONTEXT_KEY)
  void clearServerSession()
}

export function applyLoginPayload(payload: LoginPayload): SessionContext {
  const accessToken = payload.session?.access_token
  if (typeof window !== 'undefined' && accessToken) {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  }

  const prev = readStoredContext()
  const profileFromUser = payload.user?.profile_id
  const profileFromOnboarding = payload.onboarding?.profile_id
  const linkedProfileId = profileFromUser ?? profileFromOnboarding
  const linkedRequesterId = payload.user?.requester_id ?? linkedProfileId
  const profileLinked = linkedRequesterId != null && linkedProfileId != null

  const next: SessionContext = {
    ...prev,
    accessToken: accessToken || prev.accessToken,
    userId: payload.user?.user_id || prev.userId,
    requesterId: linkedRequesterId,
    profileId: linkedProfileId,
    profileLinked,
    caseId: payload.user?.case_id || prev.caseId,
    avatarUrl: payload.wechat_profile?.avatar_url || prev.avatarUrl,
  }
  writeContext(next)
  if (accessToken) {
    void persistServerSession(accessToken, next)
  }
  return getSessionContext()
}

export function applyAuthMePayload(data: {
  user?: { requester_id?: number; profile_id?: number; user_id?: string; case_id?: string }
  principal?: {
    requester_id?: number
    profile_id?: number
    user_id?: string
    user_key?: string
  }
}) {
  const patch = applyAuthPrincipalPayload(data)
  return patchSessionContext(patch)
}

function isAuthenticated(): boolean {
  return Boolean(getAccessToken())
}

function getSessionContext(): SessionContext {
  const ctx = readStoredContext()
  const accessToken = ctx.accessToken || getAccessToken() || undefined
  if (isAuthenticated()) {
    return { ...ctx, accessToken }
  }
  return {
    ...ctx,
    accessToken,
    requesterId: ctx.requesterId ?? getDefaultRequesterId(),
    profileId: ctx.profileId ?? getDefaultProfileId(),
    userId: ctx.userId ?? getDefaultUserId(),
    caseId: ctx.caseId ?? getDefaultCaseId(),
  }
}

export function patchSessionContext(patch: Partial<SessionContext>) {
  const next = { ...readStoredContext(), ...patch }
  writeContext(next)
  return next
}

export function getProfileId(): number | undefined {
  const ctx = readStoredContext()
  if (isAuthenticated()) return ctx.profileId
  return ctx.profileId ?? getDefaultProfileId()
}

export function getUserId(): string | undefined {
  const ctx = readStoredContext()
  if (isAuthenticated()) return ctx.userId
  return ctx.userId ?? getDefaultUserId()
}

/** Chat timeline: demo env user when logged out; auth user id when logged in. */
export function getChatParticipantId(): string | undefined {
  if (!isAuthenticated()) {
    const envDefault = getDefaultUserId()
    if (envDefault) return envDefault
  }
  return readStoredContext().userId
}

export function getCaseId(): string | undefined {
  const ctx = readStoredContext()
  if (isAuthenticated()) return ctx.caseId ?? getDefaultCaseId()
  return ctx.caseId ?? getDefaultCaseId()
}

export function getAvatarUrl(): string | undefined {
  return readStoredContext().avatarUrl
}
