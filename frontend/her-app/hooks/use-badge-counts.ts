'use client'

import { useCallback, useEffect, useState } from 'react'
import { fetchRelationshipsUnreadSummary, RELATIONSHIP_READ_EVENT } from '@/lib/api/endpoints/chat'
import { fetchInboxUnreadCount } from '@/lib/api/endpoints/recommendation'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { getProfileId } from '@/lib/auth/session'

export function useBadgeCounts() {
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0)
  const [relationshipsBadge, setRelationshipsBadge] = useState(0)

  const refresh = useCallback(async () => {
    const profileId = getProfileId()
    if (!profileId) {
      setInboxUnreadCount(0)
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
      const interestUnread = (interestResponse.cases || []).filter(
        (c) => c.role === 'candidate' && c.case_status === 'awaiting_reply'
      ).length

      // 合并未读数：推荐卡片 + 被动推荐
      const totalInboxUnread = inbox + interestUnread
      console.log('[Badge] 推荐卡片未读:', inbox, '被动推荐未读:', interestUnread, '总计:', totalInboxUnread)

      setInboxUnreadCount(totalInboxUnread)
      setRelationshipsBadge(relationships.total)
    } catch {
      setInboxUnreadCount(0)
      setRelationshipsBadge(0)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const onFocus = () => void refresh()
    const onReadStateChange = () => void refresh()
    const poll = window.setInterval(() => void refresh(), 30000)
    window.addEventListener('focus', onFocus)
    window.addEventListener(RELATIONSHIP_READ_EVENT, onReadStateChange)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.removeEventListener(RELATIONSHIP_READ_EVENT, onReadStateChange)
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
