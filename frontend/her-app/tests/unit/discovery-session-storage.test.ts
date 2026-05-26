import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearStoredDiscoverySessionId,
  readStoredDiscoverySessionId,
  writeStoredDiscoverySessionId,
} from '@/lib/discovery/session-storage'

describe('discovery session storage', () => {
  let storage: Record<string, string>

  beforeEach(() => {
    storage = {}
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => storage[key] ?? null,
        setItem: (key: string, value: string) => {
          storage[key] = value
        },
        removeItem: (key: string) => {
          delete storage[key]
        },
      },
    })
  })

  afterEach(() => {
    clearStoredDiscoverySessionId(9004)
    vi.unstubAllGlobals()
  })

  it('persists and reads session id per profile', () => {
    writeStoredDiscoverySessionId(9004, 'discovery-session-abc')
    expect(readStoredDiscoverySessionId(9004)).toBe('discovery-session-abc')
  })

  it('clears stored session id', () => {
    writeStoredDiscoverySessionId(9004, 'discovery-session-abc')
    clearStoredDiscoverySessionId(9004)
    expect(readStoredDiscoverySessionId(9004)).toBeNull()
  })
})
