import { fetchRelationsMine } from '@/lib/api/endpoints/relations'
import { hydrateSessionFromAuthMe } from '@/lib/auth/hydrate-session'
import { getAccessToken, getCaseId, patchSessionContext } from '@/lib/auth/session'

/** Resolve active case_id from session, auth/me, or ledger relations. */
export async function resolveCaseIdForTimeline(): Promise<string | undefined> {
  let caseId = getCaseId()
  if (caseId) return caseId

  if (getAccessToken()) {
    await hydrateSessionFromAuthMe()
    caseId = getCaseId()
    if (caseId) return caseId

    try {
      const mine = await fetchRelationsMine()
      for (const relation of mine.relations || []) {
        const activeCaseId = String(relation.active_case_id || '').trim()
        if (activeCaseId) {
          patchSessionContext({ caseId: activeCaseId })
          return activeCaseId
        }
      }
    } catch {
      // relations optional when ledger unavailable
    }
  }

  return getCaseId()
}
