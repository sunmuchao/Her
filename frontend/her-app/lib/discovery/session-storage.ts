const STORAGE_PREFIX = 'her.discovery.session'

function storageKey(profileId: number): string {
  return `${STORAGE_PREFIX}.${profileId}`
}

export function readStoredDiscoverySessionId(profileId: number): string | null {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(storageKey(profileId))?.trim()
    return value || null
  } catch {
    return null
  }
}

export function writeStoredDiscoverySessionId(profileId: number, sessionId: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey(profileId), sessionId)
  } catch {
    // Ignore quota / private mode failures.
  }
}

export function clearStoredDiscoverySessionId(profileId: number): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(storageKey(profileId))
  } catch {
    // Ignore storage failures.
  }
}
