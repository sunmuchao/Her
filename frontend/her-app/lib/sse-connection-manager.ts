'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getProfileId } from '@/lib/auth/session'

/**
 * 全局 SSE 连接管理器（Singleton模式）
 *
 * 目标：
 * - 避免多个页面重复创建SSE连接
 * - 统一管理连接、断开、重连
 * - 支持多个页面共享同一个连接
 *
 * 使用方式：
 * 1. 在应用顶层（Layout）初始化连接
 * 2. 各页面只需要监听事件，不需要创建连接
 */

const SSE_SERVER_URL = process.env.NEXT_PUBLIC_SSE_SERVER_URL || 'http://localhost:8000'

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

// 全局连接管理器（Singleton）
class SSEConnectionManager {
  private connection: EventSource | null = null
  private profileId: string | null = null
  private reconnectTimeout: NodeJS.Timeout | null = null
  private listeners: Map<string, Set<(event: ProfileSSEEvent) => void>> = new Map()
  private queryClient: any = null
  private isConnecting = false

  // 指数退避重连参数
  private reconnectAttempts = 0
  private reconnectDelay = 3000 // 初始重连延迟3秒
  private maxReconnectDelay = 30000 // 最大重连延迟30秒
  private maxReconnectAttempts = 10 // 最大重连次数10次

  /**
   * 初始化连接（只能调用一次）
   */
  init(profileId: string, queryClient: any) {
    if (this.connection || this.isConnecting) {
      console.log('[SSE Manager] 连接已存在，跳过初始化')
      return
    }

    this.profileId = profileId
    this.queryClient = queryClient
    this.connect()
  }

  /**
   * 创建SSE连接
   */
  private connect() {
    if (!this.profileId) return

    this.isConnecting = true
    console.log('[SSE Manager] 创建连接', this.profileId)

    try {
      this.connection = new EventSource(`${SSE_SERVER_URL}/sse/profile/${this.profileId}`)

      this.connection.addEventListener('message', (e) => {
        try {
          const event: ProfileSSEEvent = JSON.parse(e.data)
          this.handleEvent(event)
        } catch (err) {
          console.error('[SSE Manager] 解析事件失败', err)
        }
      })

      this.connection.addEventListener('connected', (e) => {
        console.log('[SSE Manager] 连接成功')
        this.isConnecting = false
        // 连接成功后重置重连参数
        this.reconnectAttempts = 0
        this.reconnectDelay = 3000
      })

      this.connection.onerror = (err) => {
        console.error('[SSE Manager] 连接错误', err)
        this.disconnect()

        // 检查是否达到最大重连次数
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++
          // 指数退避：延迟时间按1.5倍增长
          const delay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay)
          this.reconnectDelay = delay

          console.log(`[SSE Manager] 尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})，延迟 ${Math.round(delay/1000)}秒`)

          this.reconnectTimeout = setTimeout(() => {
            this.connect()
          }, delay)
        } else {
          console.error('[SSE Manager] 达到最大重连次数，停止重连')
          // 降级到轮询fallback（可选）
          this.startPollingFallback()
        }
      }
    } catch (err) {
      console.error('[SSE Manager] 创建连接失败', err)
      this.isConnecting = false
    }
  }

  /**
   * 处理SSE事件
   */
  private handleEvent(event: ProfileSSEEvent) {
    console.log('[SSE Manager] 收到事件', event.type)

    // 触发所有监听器
    const eventListeners = this.listeners.get(event.type)
    if (eventListeners) {
      eventListeners.forEach(callback => callback(event))
    }

    // 自动刷新相关数据（核心功能）
    if (this.queryClient) {
      switch (event.type) {
        case 'new_match':
          this.queryClient.invalidateQueries({ queryKey: ['relationships'] })
          this.queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
          break

        case 'match_status_change':
          this.queryClient.invalidateQueries({ queryKey: ['relationships'] })
          this.queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
          break

        case 'verification_passed':
        case 'verification_failed':
          this.queryClient.invalidateQueries({ queryKey: ['profile', this.profileId] })
          this.queryClient.invalidateQueries({ queryKey: ['trust-hub'] })
          this.queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
          break

        case 'profile_update':
          if (event.updated_profile_id) {
            this.queryClient.invalidateQueries({ queryKey: ['profile', event.updated_profile_id] })
            this.queryClient.invalidateQueries({ queryKey: ['relationships'] })
          }
          break

        case 'badge_update':
          if (event.badge_type && event.count !== undefined) {
            this.queryClient.setQueryData(['badge-counts', this.profileId], (old: any) => ({
              ...old,
              [event.badge_type]: event.count
            }))
          }
          break

        case 'typing_start':
        case 'typing_end':
          if (event.case_id && event.typing_user_id) {
            window.dispatchEvent(new CustomEvent(event.type, {
              detail: {
                case_id: event.case_id,
                typing_user_id: event.typing_user_id
              }
            }))
          }
          break
      }
    }
  }

  /**
   * 订阅事件
   */
  subscribe(eventType: string, callback: (event: ProfileSSEEvent) => void) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set())
    }
    this.listeners.get(eventType)!.add(callback)

    // 返回取消订阅函数
    return () => {
      this.listeners.get(eventType)?.delete(callback)
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    if (this.connection) {
      this.connection.close()
      this.connection = null
    }
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    this.isConnecting = false
    console.log('[SSE Manager] 连接已断开')
  }

  /**
   * 降级到轮询机制（SSE失败时的fallback）
   */
  private pollingInterval: NodeJS.Timeout | null = null

  private startPollingFallback() {
    console.log('[SSE Manager] 启动轮询降级机制')

    // 每30秒轮询一次关键数据
    this.pollingInterval = setInterval(() => {
      if (this.queryClient && this.profileId) {
        console.log('[SSE Manager] 执行轮询刷新')
        this.queryClient.invalidateQueries({ queryKey: ['profile', this.profileId] })
        this.queryClient.invalidateQueries({ queryKey: ['relationships'] })
        this.queryClient.invalidateQueries({ queryKey: ['badge-counts'] })
      }
    }, 30000) // 30秒轮询一次
  }

  private stopPollingFallback() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval)
      this.pollingInterval = null
      console.log('[SSE Manager] 停止轮询降级机制')
    }
  }

  /**
   * 重置连接（手动触发重连）
   */
  resetConnection() {
    this.disconnect()
    this.stopPollingFallback()
    this.reconnectAttempts = 0
    this.reconnectDelay = 3000
    this.connect()
  }

  /**
   * 检查连接状态
   */
  isConnected() {
    return this.connection?.readyState === EventSource.OPEN
  }
}

// 导出全局单例
export const sseManager = new SSEConnectionManager()

/**
 * 全局Profile实时推送Hook
 *
 * 使用统一连接管理器，避免重复连接
 */
export function useProfileRealtime() {
  const queryClient = useQueryClient()
  const profileId = getProfileId()
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    if (!profileId) return

    // 初始化全局连接
    sseManager.init(profileId, queryClient)

    // 检查连接状态
    const checkConnection = setInterval(() => {
      setIsConnected(sseManager.isConnected())
    }, 1000)

    return () => {
      clearInterval(checkConnection)
      // 注意：不要在页面卸载时断开连接，因为其他页面可能还在使用
    }
  }, [profileId, queryClient])

  return {
    isConnected,
    subscribe: sseManager.subscribe.bind(sseManager)
  }
}