import { describe, expect, test, vi } from 'vitest'
import { formatChallengeDeadline, getChallengeRemainingSeconds } from '../../components/her/verification/verification-helpers'
import { isLiveVideoChallengeExpired, parseGatewayUtcTimestamp } from '../../lib/api/endpoints/verification'

describe('verification challenge time parsing', () => {
  test('UTC timestamp is parsed consistently across UI helpers', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-03T04:20:00Z'))

    const expiresAt = '2026-07-03 04:27:00'
    const expiresAtMs = parseGatewayUtcTimestamp(expiresAt)

    expect(Number.isFinite(expiresAtMs)).toBe(true)
    expect(getChallengeRemainingSeconds(expiresAt)).toBe(420)
    expect(isLiveVideoChallengeExpired({ expires_at: expiresAt })).toBe(false)
    expect(formatChallengeDeadline(expiresAt)).not.toContain('解析失败')

    vi.useRealTimers()
  })
})
