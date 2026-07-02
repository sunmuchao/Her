'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getProfileId } from '@/lib/auth/session'
import { getSSEServerUrl } from '@/lib/sse'

/**
 * 全局 Profile SSE 实时推送 Hook
 *
 * 监听全局profile SSE事件，支持以下事件类型：
 * - new_match: 新匹配到达
 * - match_status_change: 匹配状态变化（等待回复 → 开始聊天）
 * - verification_passed: 验证通过
 * - verification_failed: 验证失败
 * - profile_update: 用户档案更新
 * - badge_update: 导航栏徽章更新
 * - typing_start: 聊天对方正在输入
 * - typing_end: 聊天对方停止输入
 *
 * 特性：
 * - 自动连接/断开
 * - 自动重连（3秒延迟）
 * - 兜底机制（SSE失败时提示用户刷新）
 */

const SSE_SERVER_URL = getSSEServerUrl()

export interface ProfileSSEEvent {
  type: string
  profile_id: string
  timestamp: string
  // 事件特定字段
  match_id?: string
  target_profile_id?: string
  status?: string
  old_status?: string
  new_status?: string
  message?: string
  updated_profile_id?: string
  updated_fields?: string[]
  badge_type?: string
  count?: number
  case_id?: string
  typing_user_id?: string
}

export function useProfileRealtime() {
  const queryClient = useQueryClient()
  const profileId = getProfileId()
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [usePolling, setUsePolling] = useState(false)

  const connect = useCallback(() => {
    if (!profileId) return

    try {
      const eventSource = new EventSource(
        `${SSE_SERVER_URL}/sse/profile/${profileId}`
      )

      eventSource.addEventListener('message', (e) => {
        try {
          const event: ProfileSSEEvent = JSON.parse(e.data)

          // 根据事件类型刷新不同的数据
          switch (event.type) {
            case 'new_match':
              // 新匹配到达，刷新关系列表和徽章
              queryClient.invalidateQueries({ queryKey: ['relationships'] })
              queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
              console.log('[SSE] 新匹配到达', event.match_id)
              break

            case 'match_status_change':
              // 匹配状态变化，刷新关系列表和徽章
              queryClient.invalidateQueries({ queryKey: ['relationships'] })
              queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
              console.log('[SSE] 匹配状态变化', event.match_id, event.old_status, '→', event.new_status)
              break

            case 'verification_passed':
              // 验证通过，刷新用户档案和徽章
              queryClient.invalidateQueries({ queryKey: ['profile', profileId] })
              queryClient.invalidateQueries({ queryKey: ['trust-hub'] })
              queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
              console.log('[SSE] 验证通过', event.message)
              break

            case 'verification_failed':
              // 验证失败，刷新用户档案和徽章
              queryClient.invalidateQueries({ queryKey: ['profile', profileId] })
              queryClient.invalidateQueries({ queryKey: ['trust-hub'] })
              queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
              console.log('[SSE] 验证失败', event.message)
              break

            case 'profile_update':
              // 对方资料更新，刷新对方档案
              if (event.updated_profile_id) {
                queryClient.invalidateQueries({ queryKey: ['profile', event.updated_profile_id] })
                queryClient.invalidateQueries({ queryKey: ['relationships'] })
                console.log('[SSE] 资料更新', event.updated_profile_id, event.updated_fields)
              }
              break

            case 'badge_update':
              // 徽章更新，直接更新徽章数据
              if (event.badge_type && event.count !== undefined) {
                queryClient.setQueryData(['badge-counts', profileId], (old: any) => ({
                  ...old,
                  [event.badge_type as string]: event.count
                }))
                console.log('[SSE] 徽章更新', event.badge_type, event.count)
              }
              break

            case 'typing_start':
              // 对方正在输入，触发自定义事件（聊天页面监听）
              if (event.case_id && event.typing_user_id) {
                window.dispatchEvent(new CustomEvent('typing_start', {
                  detail: {
                    case_id: event.case_id,
                    typing_user_id: event.typing_user_id
                  }
                }))
                console.log('[SSE] 对方正在输入', event.case_id)
              }
              break

            case 'typing_end':
              // 对方停止输入，触发自定义事件
              if (event.case_id && event.typing_user_id) {
                window.dispatchEvent(new CustomEvent('typing_end', {
                  detail: {
                    case_id: event.case_id,
                    typing_user_id: event.typing_user_id
                  }
                }))
                console.log('[SSE] 对方停止输入', event.case_id)
              }
              break

            default:
              console.log('[SSE] 未知事件类型', event.type)
          }
        } catch (err) {
          console.error('[SSE] 解析事件失败', err)
        }
      })

      eventSource.addEventListener('connected', (e) => {
        console.log('[SSE] 连接成功', profileId)
        setIsConnected(true)
        setUsePolling(false)
      })

      eventSource.onerror = (err) => {
        console.error('[SSE] 连接错误', err)
        eventSource.close()
        setIsConnected(false)

        // SSE失败，切换到轮询兜底
        setUsePolling(true)

        // 3秒后尝试重连
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('[SSE] 尝试重连')
          connect()
        }, 3000)
      }

      eventSourceRef.current = eventSource
    } catch (err) {
      console.error('[SSE] 创建连接失败', err)
      setUsePolling(true)
    }
  }, [profileId, queryClient])

  // 初始化连接
  useEffect(() => {
    connect()

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [connect])

  // 轮询兜底机制（SSE失败时）
  useEffect(() => {
    if (!usePolling || !profileId) return

    console.log('[SSE兜底] 启用30秒轮询')
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['relationships'] })
      queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
    }, 30000)

    return () => clearInterval(interval)
  }, [usePolling, profileId, queryClient])

  return {
    isConnected,
    usePolling,
    reconnect: connect
  }
}
