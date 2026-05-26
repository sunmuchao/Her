import type { SessionContext } from '@/lib/auth/session'

export type ResolvedPrincipal = {
  user_id?: string | null
  profile_id?: number | null
  requester_id?: number | null
  user_key?: string | null
  roles?: string[]
  auth_source?: string
}

export function coalesceProfileRequester(principal: ResolvedPrincipal | null | undefined): number | undefined {
  if (!principal) return undefined
  const profileId = principal.profile_id ?? principal.requester_id
  return profileId ?? undefined
}

function applyPrincipalToSession(
  principal: ResolvedPrincipal | null | undefined,
  patch: Partial<SessionContext> = {},
): Partial<SessionContext> {
  if (!principal) return patch
  const profileId = coalesceProfileRequester(principal)
  const profileLinked = profileId != null
  return {
    ...patch,
    userId: principal.user_id ?? patch.userId,
    profileId,
    requesterId: profileId,
    profileLinked: profileLinked ? true : patch.profileLinked,
  }
}

export function applyAuthPrincipalPayload(data: {
  principal?: ResolvedPrincipal | null
  user?: Partial<SessionContext> & {
    user_id?: string
    profile_id?: number
    requester_id?: number
    user_key?: string
    case_id?: string
  }
}) {
  const fromPrincipal = applyPrincipalToSession(data.principal)
  const profileId = data.user?.profile_id ?? data.user?.profileId ?? fromPrincipal.profileId
  const requesterId = data.user?.requester_id ?? data.user?.requesterId ?? profileId ?? fromPrincipal.requesterId
  return {
    ...fromPrincipal,
    userId: data.user?.user_id ?? data.user?.userId ?? fromPrincipal.userId,
    profileId,
    requesterId,
    profileLinked: requesterId != null && profileId != null,
    caseId: data.user?.case_id ?? data.user?.caseId,
  }
}
