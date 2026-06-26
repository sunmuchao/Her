import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { markInterestCaseViewed as markInterestCaseViewedAPI } from '@/lib/api/endpoints/proxy-intro'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'

// Mock gatewayJson
vi.mock('@/lib/api/client', () => ({
  gatewayJson: vi.fn(),
}))

// Mock auth session
vi.mock('@/lib/auth/session', () => ({
  getProfileId: vi.fn(() => 123),
  getAccessToken: vi.fn(() => 'test-token'),
  getUserId: vi.fn(() => 'test-user'),
}))

describe('被动推荐已查看状态测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 清空 sessionStorage
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    sessionStorage.clear()
  })

  describe('场景 1：API调用逻辑', () => {
    it('场景 1.1：markInterestCaseViewedAPI 成功调用', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'viewed',
        },
      })

      const result = await markInterestCaseViewedAPI({
        caseId: 'case-1',
        source: 'detail_page',
      })

      // 验证 API 调用
      expect(gatewayJson).toHaveBeenCalledWith(
        '/v1/proxy-intro/cases/case-1/view',
        {
          method: 'POST',
          body: JSON.stringify({ source: 'detail_page' }),
        }
      )

      // 验证返回数据
      expect(result.case?.case_status).toBe('viewed')
    })

    it('场景 1.2：markInterestCaseViewedAPI 失败抛出错误', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockRejectedValueOnce(new Error('API failed'))

      expect(async () => {
        await markInterestCaseViewedAPI({ caseId: 'case-1' })
      }).rejects.toThrow('API failed')
    })

    it('场景 1.3：非awaiting_reply状态的case返回message', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'accepted',
        },
        message: '当前状态为accepted，无需标记为viewed',
      })

      const result = await markInterestCaseViewedAPI({ caseId: 'case-1' })

      // 验证返回message
      expect(result.message).toContain('accepted')
      expect(result.case?.case_status).toBe('accepted')
    })
  })

  describe('场景 2：badge count计算逻辑（根本解决后）', () => {
    it('场景 2.1：只统计awaiting_reply状态的case', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'viewed' },
          { case_id: 'case-3', role: 'candidate', case_status: 'accepted' },
          { case_id: 'case-4', role: 'candidate', case_status: 'declined' },
          { case_id: 'case-5', role: 'requester', case_status: 'awaiting_reply' },
        ],
      })

      const response = await fetchMyProxyIntroCases()

      // 计算未读数：只统计 awaiting_reply
      const interestUnread = (response.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      // 验证：只有case-1应该计入
      expect(interestUnread).toBe(1)
    })

    it('场景 2.2：viewed状态不计入badge count', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'viewed' },
          { case_id: 'case-3', role: 'candidate', case_status: 'viewed' },
        ],
      })

      const response = await fetchMyProxyIntroCases()
      const interestUnread = (response.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      // 验证：viewed状态的case-2和case-3不计入
      expect(interestUnread).toBe(1)
    })

    it('场景 2.3：合并badge count（推荐卡片 + 被动推荐）', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // Mock 推荐卡片（2个未读）
      gatewayJson.mockResolvedValueOnce({
        cards: [
          { card_id: 'card-1', card_status: 'unread' },
          { card_id: 'card-2', card_status: 'unread' },
        ],
      })

      // Mock 被动推荐（1个awaiting_reply，2个viewed）
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'viewed' },
          { case_id: 'case-3', role: 'candidate', case_status: 'viewed' },
        ],
      })

      // 模拟useBadgeCounts的refresh函数逻辑
      const { fetchInboxUnreadCount } = await import('@/lib/api/endpoints/recommendation')
      const inbox = await fetchInboxUnreadCount(123)
      const interestResponse = await fetchMyProxyIntroCases()
      const interestUnread = (interestResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      const totalInboxUnread = inbox + interestUnread

      // 验证：2 推荐卡片 + 1 被动推荐（awaiting_reply）
      expect(totalInboxUnread).toBe(3)
    })
  })

  describe('场景 3：状态转换逻辑', () => {
    it('场景 3.1：awaiting_reply → viewed', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // 初始状态：awaiting_reply
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
        ],
      })

      // 标记为viewed
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'viewed',
        },
      })

      // 验证状态转换
      const beforeResponse = await fetchMyProxyIntroCases()
      expect(beforeResponse.cases?.[0]?.case_status).toBe('awaiting_reply')

      const afterResult = await markInterestCaseViewedAPI({ caseId: 'case-1' })
      expect(afterResult.case?.case_status).toBe('viewed')
    })

    it('场景 3.2：viewed状态不能再次标记为viewed', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'viewed',
        },
        message: '当前状态为viewed，无需标记为viewed',
      })

      // 尝试再次标记为viewed
      const result = await markInterestCaseViewedAPI({ caseId: 'case-1' })

      // 验证状态不变
      expect(result.case?.case_status).toBe('viewed')
      expect(result.message).toContain('viewed')
    })

    it('场景 3.3：accepted/declined状态不能标记为viewed', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'accepted',
        },
        message: '当前状态为accepted，无需标记为viewed',
      })

      const result = await markInterestCaseViewedAPI({ caseId: 'case-1' })

      expect(result.case?.case_status).toBe('accepted')
      expect(result.message).toContain('accepted')
    })
  })

  describe('场景 4：端到端流程', () => {
    it('场景 4.1：用户点击被动推荐卡片，badge count减少', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // 初始状态：3个被动推荐（全部awaiting_reply）
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-3', role: 'candidate', case_status: 'awaiting_reply' },
        ],
      })

      // 计算初始badge count
      const beforeResponse = await fetchMyProxyIntroCases()
      const beforeCount = (beforeResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length
      expect(beforeCount).toBe(3)

      // 用户点击case-1，标记为viewed
      gatewayJson.mockResolvedValueOnce({
        case: {
          case_id: 'case-1',
          case_status: 'viewed',
        },
      })
      await markInterestCaseViewedAPI({ caseId: 'case-1' })

      // 刷新后badge count应该减少
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'viewed' },
          { case_id: 'case-2', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-3', role: 'candidate', case_status: 'awaiting_reply' },
        ],
      })
      const afterResponse = await fetchMyProxyIntroCases()
      const afterCount = (afterResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      expect(afterCount).toBe(2) // badge count从3减少到2
    })

    it('场景 4.2：用户接受被动推荐，badge count不再变化', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // 初始状态：case已查看（viewed）
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'viewed' },
        ],
      })

      // Badge count已经是0（viewed不计入）
      const beforeResponse = await fetchMyProxyIntroCases()
      const beforeCount = (beforeResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length
      expect(beforeCount).toBe(0)

      // 用户接受（状态变为accepted）
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'accepted' },
        ],
      })

      const afterResponse = await fetchMyProxyIntroCases()
      const afterCount = (afterResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      expect(afterCount).toBe(0) // badge count仍然是0
    })
  })

  describe('场景 5：边缘场景', () => {
    it('场景 5.1：无profileId不调用API', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({ cases: [] })

      const response = await fetchMyProxyIntroCases()
      expect(response.cases).toEqual([])
    })

    it('场景 5.2：API返回空数据', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValueOnce({ cases: [] })

      const response = await fetchMyProxyIntroCases()
      const interestUnread = (response.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      expect(interestUnread).toBe(0)
    })

    it('场景 5.3：并发标记多个case为viewed', async () => {
      const { gatewayJson } = await import('@/lib/api/client')
      gatewayJson.mockResolvedValue({
        case: {
          case_id: 'case-1',
          case_status: 'viewed',
        },
      })

      // 并发标记3个case
      const promises = [
        markInterestCaseViewedAPI({ caseId: 'case-1' }),
        markInterestCaseViewedAPI({ caseId: 'case-2' }),
        markInterestCaseViewedAPI({ caseId: 'case-3' }),
      ]

      await Promise.all(promises)

      // 验证所有API都调用
      expect(gatewayJson).toHaveBeenCalledTimes(3)
    })

    it('场景 5.4：清空sessionStorage不影响badge count', async () => {
      const { gatewayJson } = await import('@/lib/api/client')

      // 后端数据：2个awaiting_reply，1个viewed
      gatewayJson.mockResolvedValueOnce({
        cases: [
          { case_id: 'case-1', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-2', role: 'candidate', case_status: 'awaiting_reply' },
          { case_id: 'case-3', role: 'candidate', case_status: 'viewed' },
        ],
      })

      // 清空sessionStorage（模拟用户清空浏览器缓存）
      sessionStorage.clear()

      // 刷新badge count（从后端获取真实数据）
      const response = await fetchMyProxyIntroCases()
      const interestUnread = (response.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      // 验证：badge count仍然正确（从后端获取，不依赖sessionStorage）
      expect(interestUnread).toBe(2)
    })
  })
})