import { isMockFallbackAllowed } from '@/lib/env'

export function canUseMockFallback(): boolean {
  return isMockFallbackAllowed()
}
