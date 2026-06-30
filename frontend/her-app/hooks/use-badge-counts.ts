'use client'

import { useState, useCallback, useEffect } from 'react'
import { fetchRelationshipsUnreadSummary, RELATIONSHIP_READ_EVENT } from '@/lib/api/endpoints/chat'
import { fetchInboxUnreadCount, RECOMMENDATION_READ_EVENT } from '@/lib/api/endpoints/recommendation'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { getAccessToken, getProfileId } from '@/lib/auth/session'
import { confirmSessionOrRedirectToWelcome } from '@/lib/auth/confirm-session'
import { isAuthRequiredGatewayError } from '@/lib/api/errors'

// 全局徽章计数状态（不再支持乐观更新，完全依赖后端真实数据）
let globalInboxUnreadCount = 0
let globalRelationshipsBadge = 0
const listeners = new Set<() => void>()

export function useBadgeCounts() {
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0)
  const [relationshipsBadge, setRelationshipsBadge] = useState(0)

  const refresh = useCallback(async () => {
    if (!getAccessToken()) {
      setInboxUnreadCount(0)
      setRelationshipsBadge(0)
      globalInboxUnreadCount = 0
      return
    }
    const profileId = getProfileId()
    if (!profileId) {
      setInboxUnreadCount(0)
      setRelationshipsBadge(0)
      globalInboxUnreadCount = 0
      return
    }
    try {
      // 加载推荐卡片未读数
      const inboxPromise = fetchInboxUnreadCount(profileId)
      // 加载被动推荐 case（有人想认识你）未读数
      const interestPromise = fetchMyProxyIntroCases()
      const relationshipsPromise = fetchRelationshipsUnreadSummary()

      const [inbox, interestResponse, relationships] = await Promise.all([
        inboxPromise,
        interestPromise,
        relationshipsPromise,
      ])

      // 计算被动推荐未读数：role === 'candidate' && case_status === 'awaiting_reply'
      // 注意：viewed状态的case不算未读（用户已查看但未决定）
      const interestUnread = (interestResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'  // 只统计未查看状态
      ).length

      // 日志7：打印inbox badge计算详情
      console.log('[Badge Debug] Inbox badge:', {
        recommendation_cards_unread: inbox,
        passive_recommendation_unread: interestUnread,
        total_inbox_unread: inbox + interestUnread,
      })

      // 合并未读数：推荐卡片 + 被动推荐
      const totalInboxUnread = inbox + interestUnread
      console.log('[Badge] 推荐卡片未读:', inbox, '被动推荐未读:', interestUnread, '总计:', totalInboxUnread)

      setInboxUnreadCount(totalInboxUnread)

      // 日志8：打印relationships badge详情
      console.log('[Badge Debug] Relationships badge:', {
        pending: relationships.pendingCount,
        chat_unread: relationships.chatUnread,
        total: relationships.total,
        by_case_id: relationships.byCaseId,
      })

      setRelationshipsBadge(relationships.total)
      globalInboxUnreadCount = totalInboxUnread
      sessionStorage.setItem('inbox-unread-count', String(totalInboxUnread))
    } catch (error) {
      if (isAuthRequiredGatewayError(error)) {
        const sessionStillValid = await confirmSessionOrRedirectToWelcome()
        if (sessionStillValid) {
          console.warn('[Badge] 后台刷新鉴权失败，保留当前会话，等待下次重试', error)
        }
        return
      }
      setInboxUnreadCount(0)
      setRelationshipsBadge(0)
      globalInboxUnreadCount = 0
    }
  }, [])

  // 监听全局状态变化
  useEffect(() => {
    const listener = () => {
      setInboxUnreadCount(globalInboxUnreadCount)
    }
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  useEffect(() => {
    // 初始化时立即刷新，获取真实数据（不依赖 sessionStorage）
    void refresh()
    const onFocus = () => void refresh()
    const onReadStateChange = () => void refresh()
    const poll = window.setInterval(() => void refresh(), 30000)
    window.addEventListener('focus', onFocus)
    window.addEventListener(RELATIONSHIP_READ_EVENT, onReadStateChange)
    window.addEventListener(RECOMMENDATION_READ_EVENT, onReadStateChange)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener(RELATIONSHIP_READ_EVENT, onReadStateChange)
      window.removeEventListener(RECOMMENDATION_READ_EVENT, onReadStateChange)
      window.clearInterval(poll)
    }
  }, [refresh])

  return {
    inboxUnreadCount,
    relationshipsBadge,
    setRelationshipsBadge,
    refreshBadges: refresh,
  }
}
