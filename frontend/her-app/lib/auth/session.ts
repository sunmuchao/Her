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

/** Whether the logged-in user has a backend-linked profile/requester (safe to send Bearer on data APIs). */
export function hasLinkedProfileIdentity(): boolean {
  return readStoredContext().profileLinked === true
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
  }
  writeContext(next)
  if (accessToken) {
    void persistServerSession(accessToken, next)
  }
  return getSessionContext()
}

export function applyAuthMePayload(data: {
  user?: { requester_id?: number; profile_id?: number; user_id?: string; case_id?: string }
}) {
  const user = data.user || {}
  const profileId = user.profile_id
  const requesterId = user.requester_id ?? profileId
  const profileLinked = requesterId != null && profileId != null
  return patchSessionContext({
    userId: user.user_id,
    requesterId,
    profileId,
    profileLinked,
    caseId: user.case_id,
  })
}

export function getSessionContext(): SessionContext {
  const ctx = readStoredContext()
  return {
    ...ctx,
    accessToken: ctx.accessToken || getAccessToken() || undefined,
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

export function getRequesterId(): number | undefined {
  return getSessionContext().requesterId
}

export function getProfileId(): number | undefined {
  return getSessionContext().profileId
}

export function getUserId(): string | undefined {
  return getSessionContext().userId
}

/** Chat timeline uses case member ids (e.g. user-a), not auth account ids (usr-...). */
export function getChatParticipantId(): string | undefined {
  const envDefault = getDefaultUserId()
  if (envDefault) return envDefault
  return readStoredContext().userId
}

export function getCaseId(): string | undefined {
  return getSessionContext().caseId
}
