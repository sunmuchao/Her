'use client'

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getProfileId, getAccessToken } from '@/lib/auth/session'
import { sseManager } from '@/lib/sse-connection-manager'

/**
 * SSE连接初始化组件
 *
 * 在应用顶层使用，初始化全局SSE连接
 * 所有页面共享同一个连接，避免重复连接
 */
export function SSEInitializer() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const profileId = getProfileId()
    const accessToken = getAccessToken()

    // 只有登录后才初始化SSE连接
    if (profileId && accessToken) {
      console.log('[SSE Initializer] 初始化全局SSE连接', profileId)
      sseManager.init(String(profileId), queryClient)
    }

    // 注意：不要在组件卸载时断开连接，因为整个应用都在使用
  }, [queryClient])

  return null // 不渲染任何内容
}