'use client'

import { useEffect, useState } from 'react'

/**
 * 页面可见性检测 hook
 *
 * 用于检测页面是否在浏览器前台可见，避免后台轮询浪费资源。
 *
 * @returns {boolean} isVisible - 页面是否可见
 *
 * @example
 * ```typescript
 * const isVisible = usePageVisibility()
 *
 * // 仅在页面可见时执行操作
 * if (isVisible) {
 *   // 执行可见性相关的操作
 * }
 * ```
 */
export function usePageVisibility() {
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    // 检查 document 是否可用（SSR 环境）
    if (typeof document === 'undefined') {
      return
    }

    // 初始化时检查当前状态
    setIsVisible(!document.hidden)

    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden)
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  return isVisible
}