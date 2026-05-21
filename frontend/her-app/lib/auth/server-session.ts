import type { SessionContext } from '@/lib/auth/session'

export async function persistServerSession(accessToken: string, context: SessionContext) {
  if (typeof window === 'undefined') return
  await fetch('/api/auth/session', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      access_token: accessToken,
      context: {
        userId: context.userId,
        requesterId: context.requesterId,
        profileId: context.profileId,
        caseId: context.caseId,
        profileLinked: context.profileLinked,
      },
    }),
  })
}

export async function clearServerSession() {
  if (typeof window === 'undefined') return
  await fetch('/api/auth/session', { method: 'DELETE', credentials: 'include' })
}
