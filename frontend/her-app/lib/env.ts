import { z } from 'zod'

const publicEnvSchema = z.object({
  NEXT_PUBLIC_ALLOW_MOCK_FALLBACK: z
    .enum(['true', 'false'])
    .optional()
    .transform((v) => v === 'true'),
  NEXT_PUBLIC_ENABLE_DEMO_NAV: z
    .enum(['true', 'false'])
    .optional()
    .transform((v) => v === 'true'),
  NEXT_PUBLIC_USE_AUTH_STUB: z
    .enum(['true', 'false'])
    .optional()
    .transform((v) => v === 'true'),
  NEXT_PUBLIC_HER_REQUESTER_ID: z.string().optional(),
  NEXT_PUBLIC_HER_PROFILE_ID: z.string().optional(),
  NEXT_PUBLIC_HER_USER_ID: z.string().optional(),
  NEXT_PUBLIC_HER_CASE_ID: z.string().optional(),
  NEXT_PUBLIC_E2E_GATEWAY_AUTH: z
    .enum(['true', 'false'])
    .optional()
    .transform((v) => v === 'true'),
})

type PublicEnv = z.infer<typeof publicEnvSchema>

let cached: PublicEnv | null = null

function getPublicEnv(): PublicEnv {
  if (cached) return cached
  cached = publicEnvSchema.parse({
    NEXT_PUBLIC_ALLOW_MOCK_FALLBACK: process.env.NEXT_PUBLIC_ALLOW_MOCK_FALLBACK,
    NEXT_PUBLIC_ENABLE_DEMO_NAV: process.env.NEXT_PUBLIC_ENABLE_DEMO_NAV,
    NEXT_PUBLIC_USE_AUTH_STUB: process.env.NEXT_PUBLIC_USE_AUTH_STUB,
    NEXT_PUBLIC_HER_REQUESTER_ID: process.env.NEXT_PUBLIC_HER_REQUESTER_ID,
    NEXT_PUBLIC_HER_PROFILE_ID: process.env.NEXT_PUBLIC_HER_PROFILE_ID,
    NEXT_PUBLIC_HER_USER_ID: process.env.NEXT_PUBLIC_HER_USER_ID,
    NEXT_PUBLIC_HER_CASE_ID: process.env.NEXT_PUBLIC_HER_CASE_ID,
    NEXT_PUBLIC_E2E_GATEWAY_AUTH: process.env.NEXT_PUBLIC_E2E_GATEWAY_AUTH,
  })
  return cached
}

export function isDemoNavEnabled(): boolean {
  if (process.env.NODE_ENV === 'development') return true
  return getPublicEnv().NEXT_PUBLIC_ENABLE_DEMO_NAV
}

export function isMockFallbackAllowed(): boolean {
  if (process.env.NODE_ENV === 'production') return false
  return getPublicEnv().NEXT_PUBLIC_ALLOW_MOCK_FALLBACK
}

export function isAuthStubEnabled(): boolean {
  if (process.env.NODE_ENV === 'production') return isE2EGatewayAuthEnabled()
  return getPublicEnv().NEXT_PUBLIC_USE_AUTH_STUB
}

/** CI E2E only: allow stub auth codes against gateway HER_AUTH_* stub while mock fallback stays off. */
export function isE2EGatewayAuthEnabled(): boolean {
  return getPublicEnv().NEXT_PUBLIC_E2E_GATEWAY_AUTH
}

export function getDefaultRequesterId(): number | undefined {
  const raw = getPublicEnv().NEXT_PUBLIC_HER_REQUESTER_ID
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

export function getDefaultProfileId(): number | undefined {
  const raw = getPublicEnv().NEXT_PUBLIC_HER_PROFILE_ID
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : undefined
}

export function getDefaultUserId(): string | undefined {
  const raw = getPublicEnv().NEXT_PUBLIC_HER_USER_ID?.trim()
  return raw || undefined
}

export function getDefaultCaseId(): string | undefined {
  const raw = getPublicEnv().NEXT_PUBLIC_HER_CASE_ID?.trim()
  return raw || undefined
}
