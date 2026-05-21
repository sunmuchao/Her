const STORAGE_KEY = 'her_device_id'

export function getDeviceId(): string {
  if (typeof window === 'undefined') {
    return 'web-ssr'
  }
  const existing = window.localStorage.getItem(STORAGE_KEY)
  if (existing) {
    return existing
  }
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? `web-${crypto.randomUUID()}`
      : `web-${Date.now()}`
  window.localStorage.setItem(STORAGE_KEY, id)
  return id
}
