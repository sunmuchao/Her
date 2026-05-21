'use client'

import { useCallback, useEffect, useState } from 'react'
import { fetchRelationshipsUnreadCount } from '@/lib/api/endpoints/chat'
import { fetchInboxUnreadCount } from '@/lib/api/endpoints/recommendation'
import { getRequesterId } from '@/lib/auth/session'

export function useBadgeCounts() {
  const [inboxUnreadCount, setInboxUnreadCount] = useState(0)
  const [relationshipsBadge, setRelationshipsBadge] = useState(0)

  const refresh = useCallback(async () => {
    const requesterId = getRequesterId()
    if (!requesterId) {
      setInboxUnreadCount(0)
      return
    }
    try {
      const [inbox, relationships] = await Promise.all([
        fetchInboxUnreadCount(requesterId),
        fetchRelationshipsUnreadCount(),
      ])
      setInboxUnreadCount(inbox)
      setRelationshipsBadge(relationships)
    } catch {
      setInboxUnreadCount(0)
      setRelationshipsBadge(0)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const onFocus = () => void refresh()
    const poll = window.setInterval(() => void refresh(), 30000)
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
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
