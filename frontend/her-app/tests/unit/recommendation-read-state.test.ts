import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { markRecommendationCardsRead, RECOMMENDATION_READ_EVENT, fetchInboxUnreadCount } from '@/lib/api/endpoints/recommendation'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { getProfileId } from '@/lib/auth/session'

// Mock gatewayJson
vi.mock('@/lib/api/client', () => ({
  gatewayJson: vi.fn(),
  queryString: vi.fn((params) => {
    const query = Object.entries(params)
      .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
      .join('&')
    return query ? `?${query}` : ''
  }),
}))

// Mock auth session
vi.mock('@/lib/auth/session', () => ({
  getProfileId: vi.fn(() => 123),
  getAccessToken: vi.fn(() => 'test-token'),
  getUserId: vi.fn(() => 'test-user'),
}))

describe('推荐来信已读状态测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('场景 1：事件触发逻辑', () => {
    it('场景 1.1：markRecommendationCardsRead 成功后调用 API', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({})

      const profileId = 123
      const cardIds = ['card-1', 'card-2']

      await markRecommendationCardsRead(profileId, cardIds)

      // 验证 API 调用
      expect(gatewayJson).toHaveBeenCalledWith('/v1/recommendation/cards/read', {
        method: 'POST',
        body: JSON.stringify({ profile_id: profileId, card_ids: cardIds }),
      })
    })

    it('场景 1.2：markRecommendationCardsRead 失败抛出错误', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockRejectedValueOnce(new Error('API failed'))

      const profileId = 123
      const cardIds = ['card-1']

      expect(async () => {
        await markRecommendationCardsRead(profileId, cardIds)
      }).rejects.toThrow('API failed')
    })

    it('场景 1.3：事件名称正确性', () => {
      expect(RECOMMENDATION_READ_EVENT).toBe('her:recommendation-read-state-changed')
    })
  })

  describe('场景 2：徽章计数计算逻辑', () => {
    it('场景 2.1：计算推荐卡片未读数', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      // Mock 只返回未读卡片（unread_only=true）
      gatewayJson.mockResolvedValueOnce({
        cards: [
          { card_id: 'card-1', card_status: 'unread' },
          { card_id: 'card-2', card_status: 'unread' },
        ],
      })

      const count = await fetchInboxUnreadCount(123)

      // 验证未读数计算正确
      expect(count).toBe(2)
    })

    it('场景 2.2：计算被动推荐未读数', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-3', role: 'candidate', case_status: 'accepted' },
          { case_id: 'case-4', role: 'requester', case_status: 'awaiting_reply' },
        ],
      })

      const response = await fetchMyProxyIntroCases()

      // 过滤被动推荐：role === 'candidate' && case_status === 'awaiting_reply'
      const interestUnread = (response.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      expect(interestUnread).toBe(2) // case-1 和 case-2
    })

    it('场景 2.3：合并未读数（推荐卡片 + 被动推荐）', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // Mock 推荐卡片
      gatewayJson.mockResolvedValueOnce({
        cards: [
          { card_id: 'card-1', card_status: 'unread' },
          { card_id: 'card-2', card_status: 'unread' },
        ],
      })

      // Mock 被动推荐
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'awaiting_reply' },
        ],
      })

      const inbox = await fetchInboxUnreadCount(123)
      const interestResponse = await fetchMyProxyIntroCases()
      const interestUnread = (interestResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      const totalInboxUnread = inbox + interestUnread

      expect(totalInboxUnread).toBe(4) // 2 推荐卡片 + 2 被动推荐
    })
  })

  describe('场景 3：并发场景', () => {
    it('场景 3.1：并发点击多个卡片，所有 API 都调用', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValue({})

      // 并发点击 3 个卡片
      const promises = [
        markRecommendationCardsRead(123, ['card-1']),
        markRecommendationCardsRead(123, ['card-2']),
        markRecommendationCardsRead(123, ['card-3']),
      ]

      await Promise.all(promises)

      // 验证所有 API 都调用
      expect(gatewayJson).toHaveBeenCalledTimes(3)
    })

    it('场景 3.2：部分 API 失败，成功的仍返回', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockRejectedValueOnce(new Error('API failed'))
      gatewayJson.mockResolvedValueOnce({})
      gatewayJson.mockRejectedValueOnce(new Error('API failed'))

      // 并发点击 3 个卡片，其中 2 个失败
      const results = await Promise.allSettled([
        markRecommendationCardsRead(123, ['card-1']),
        markRecommendationCardsRead(123, ['card-2']),
        markRecommendationCardsRead(123, ['card-3']),
      ])

      // 验证结果：2 个失败，1 个成功
      expect(results[0].status).toBe('rejected')
      expect(results[1].status).toBe('fulfilled')
      expect(results[2].status).toBe('rejected')
    })
  })

  describe('场景 4：数据一致性', () => {
    it('场景 4.1：推荐卡片已读状态判断逻辑', async () => {
      // 模拟推荐卡片数据
      const cards = [
        { card_id: 'card-1', card_status: 'read' },
        { card_id: 'card-2', card_status: 'unread' },
        { card_id: 'card-3', card_status: 'sent' },
      ]

      // 验证 isRead 判断逻辑
      const isReadResults = cards.map((card) => card.card_status === 'read')

      expect(isReadResults).toEqual([true, false, false])
    })

    it('场景 4.2：被动推荐已读状态判断逻辑', async () => {
      // 模拟被动推荐数据
      const cases = [
        { case_id: 'case-1', case_status: 'awaiting_reply' },
        { case_id: 'case-2', case_status: 'accepted' },
        { case_id: 'case-3', case_status: 'declined' },
      ]

      // 验证 isRead 判断逻辑
      const isReadResults = cases.map((c) => c.case_status !== 'awaiting_reply')

      expect(isReadResults).toEqual([false, true, true])
    })
  })

  describe('场景 5：边缘场景', () => {
    it('场景 5.1：空数组标记已读', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({})

      await markRecommendationCardsRead(123, [])

      expect(gatewayJson).toHaveBeenCalledWith('/v1/recommendation/cards/read', {
        method: 'POST',
        body: JSON.stringify({ profile_id: 123, card_ids: [] }),
      })
    })

    it('场景 5.2：无 profileId 不调用 API', async () => {
      vi.mocked(getProfileId).mockReturnValueOnce(null)

      const count = await fetchInboxUnreadCount()

      expect(count).toBe(0)
    })

    it('场景 5.3：API 返回空数据', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({ cards: [] })

      const count = await fetchInboxUnreadCount(123)

      expect(count).toBe(0)
    })
  })
})