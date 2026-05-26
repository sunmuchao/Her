import { afterEach, describe, expect, it, vi } from 'vitest'

describe('lib/env', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('disallows mock fallback in production', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('NEXT_PUBLIC_ALLOW_MOCK_FALLBACK', 'true')
    const { isMockFallbackAllowed } = await import('@/lib/env')
    expect(isMockFallbackAllowed()).toBe(false)
  })

  it('allows mock fallback only in development with flag', async () => {
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('NEXT_PUBLIC_ALLOW_MOCK_FALLBACK', 'true')
    const { isMockFallbackAllowed } = await import('@/lib/env')
    expect(isMockFallbackAllowed()).toBe(true)
  })

  it('enables demo nav in development without extra flag', async () => {
    vi.stubEnv('NODE_ENV', 'development')
    const { isDemoNavEnabled } = await import('@/lib/env')
    expect(isDemoNavEnabled()).toBe(true)
  })

  it('disallows auth stub in production without e2e gateway flag', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('NEXT_PUBLIC_USE_AUTH_STUB', 'true')
    vi.stubEnv('NEXT_PUBLIC_E2E_GATEWAY_AUTH', 'false')
    const { isAuthStubEnabled } = await import('@/lib/env')
    expect(isAuthStubEnabled()).toBe(false)
  })

  it('allows e2e gateway auth in production build when explicitly enabled', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('NEXT_PUBLIC_E2E_GATEWAY_AUTH', 'true')
    const { isE2EGatewayAuthEnabled, isAuthStubEnabled } = await import('@/lib/env')
    expect(isE2EGatewayAuthEnabled()).toBe(true)
    expect(isAuthStubEnabled()).toBe(true)
  })
})
