export type HerRuntimeContext = {
  requesterId?: number
  profileId?: number
  userId?: string
  caseId?: string
}

export function parseOptionalInt(value: string | null | undefined): number | undefined {
  if (!value) {
    return undefined
  }
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined
  }
  return parsed
}

export function envText(value: string | undefined): string | undefined {
  const text = String(value || '').trim()
  return text || undefined
}
