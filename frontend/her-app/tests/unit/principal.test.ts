import { describe, expect, it } from 'vitest'
import { applyAuthPrincipalPayload, coalesceProfileRequester } from '@/lib/auth/principal'

describe('principal session helpers', () => {
  it('coalesces profile_id and requester_id', () => {
    expect(coalesceProfileRequester({ profile_id: 7, requester_id: 9 })).toBe(7)
    expect(coalesceProfileRequester({ requester_id: 12 })).toBe(12)
  })

  it('merges auth/me principal block into session patch', () => {
    const patch = applyAuthPrincipalPayload({
      user: { user_id: 'u-1' },
      principal: { user_id: 'u-1', profile_id: 42, requester_id: 42, user_key: '42' },
    })
    expect(patch.userId).toBe('u-1')
    expect(patch.profileId).toBe(42)
    expect(patch.requesterId).toBe(42)
    expect(patch.profileLinked).toBe(true)
  })
})
