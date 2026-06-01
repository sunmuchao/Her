import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth/session', () => ({
  getAccessToken: vi.fn(),
  getChatParticipantId: vi.fn(),
  getUserId: vi.fn(),
}))

vi.mock('@/lib/api/endpoints/proxy-intro', () => ({
  fetchMyProxyIntroCases: vi.fn(),
}))

import { getAccessToken } from '@/lib/auth/session'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { fetchRelationshipsUnreadSummary } from '@/lib/api/endpoints/chat'

describe('fetchRelationshipsUnreadSummary', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('returns zero summary without access token', async () => {
    vi.mocked(getAccessToken).mockReturnValue(null)

    await expect(fetchRelationshipsUnreadSummary()).resolves.toEqual({
      total: 0,
      chatUnread: 0,
      pendingCount: 0,
      byCaseId: {},
    })
    expect(fetchMyProxyIntroCases).not.toHaveBeenCalled()
  })
})
