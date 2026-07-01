'use client'

import { useEffect, useRef, useState } from 'react'
import { getProfileId } from '@/lib/auth/session'

/**
 * 全局SSE订阅Hook
 *
 * 在App Shell级别建立全局SSE连接（基于profile_id），所有页面共享
 * 支持多种事件类型：
 * - case_status_update: 案件状态更新（接受/拒绝）
 * - new_recommendation: 新推荐卡片
 * - candidates_ready: 候选人准备好了
 */
export function useGlobalSSE() {
  const [isConnected, setIsConnected] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const profileId = getProfileId()
    if (!profileId) return

    // 创建SSE连接
    const sseUrl = `${process.env.NEXT_PUBLIC_SSE_SERVER_URL || 'http://localhost:8081'}/sse/profile/${profileId}`
    const eventSource = new EventSource(sseUrl)
    eventSourceRef.current = eventSource

    eventSource.addEventListener('connected', (e) => {
      console.log('[Global SSE] Connected:', e.data)
      setIsConnected(true)
    })

    eventSource.addEventListener('message', (e) => {
      try {
        const data = JSON.parse(e.data)
        console.log('[Global SSE] Message received:', data)

        // 根据事件类型分发
        if (data.type === 'case_status_update') {
          // 案件状态更新：触发关系页面刷新事件
          window.dispatchEvent(new CustomEvent('her:case-status-updated', {
            detail: {
              caseId: data.case_id,
              newStatus: data.new_status,
              candidateId: data.candidate_id,
              message: data.message,
              timestamp: data.timestamp,
            },
          }))
        } else if (data.type === 'new_recommendation') {
          // 新推荐卡片：触发推荐卡片刷新事件
          window.dispatchEvent(new CustomEvent('her:recommendation-read-state-changed', {
            detail: {
              profileId: data.profile_id,
              newCards: data.cards,
            },
          }))
        } else if (data.type === 'candidates_ready') {
          // 候选人准备好了：触发discovery页面刷新事件
          window.dispatchEvent(new CustomEvent('her:discovery-candidates-ready', {
            detail: {
              sessionId: data.session_id,
              profileId: data.profile_id,
            },
          }))
        }
      } catch (err) {
        console.error('[Global SSE] Parse error:', err)
      }
    })

    eventSource.addEventListener('heartbeat', (e) => {
      console.log('[Global SSE] Heartbeat:', e.data)
    })

    eventSource.onerror = (e) => {
      const readyState = eventSource.readyState
      if (readyState === EventSource.CONNECTING) {
        console.warn('[Global SSE] Reconnecting...', { readyState })
      } else if (readyState === EventSource.CLOSED) {
        console.error('[Global SSE] Closed', { readyState, event: e })
      } else {
        console.warn('[Global SSE] Error event', { readyState, event: e })
      }
      setIsConnected(false)
      // EventSource会自动重连
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
  }, [])

  return {
    isConnected,
  }
}