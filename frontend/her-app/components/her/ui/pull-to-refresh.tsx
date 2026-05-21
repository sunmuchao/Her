'use client'

import { useState, useRef, useCallback, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

interface PullToRefreshProps {
  children: ReactNode
  onRefresh: () => Promise<void>
  className?: string
  pullThreshold?: number
  maxPull?: number
}

export function PullToRefresh({
  children,
  onRefresh,
  className,
  pullThreshold = 80,
  maxPull = 120
}: PullToRefreshProps) {
  const [pullDistance, setPullDistance] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const startY = useRef(0)
  const isPulling = useRef(false)

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (containerRef.current?.scrollTop === 0 && !isRefreshing) {
      startY.current = e.touches[0].clientY
      isPulling.current = true
    }
  }, [isRefreshing])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isPulling.current || isRefreshing) return
    
    const currentY = e.touches[0].clientY
    const diff = currentY - startY.current
    
    if (diff > 0) {
      e.preventDefault()
      const resistance = 0.5
      const newDistance = Math.min(diff * resistance, maxPull)
      setPullDistance(newDistance)
    }
  }, [isRefreshing, maxPull])

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling.current) return
    isPulling.current = false

    if (pullDistance >= pullThreshold && !isRefreshing) {
      setIsRefreshing(true)
      setPullDistance(60)
      
      try {
        await onRefresh()
      } finally {
        setIsRefreshing(false)
        setPullDistance(0)
      }
    } else {
      setPullDistance(0)
    }
  }, [pullDistance, pullThreshold, isRefreshing, onRefresh])

  const progress = Math.min(pullDistance / pullThreshold, 1)
  const shouldTrigger = pullDistance >= pullThreshold

  return (
    <div
      ref={containerRef}
      className={cn('relative overflow-auto', className)}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Pull indicator */}
      <div
        className="absolute left-1/2 -translate-x-1/2 flex items-center justify-center z-10 transition-opacity"
        style={{
          top: Math.max(pullDistance - 48, 8),
          opacity: pullDistance > 20 ? 1 : 0
        }}
      >
        <div
          className={cn(
            'w-10 h-10 rounded-full bg-card shadow-lg flex items-center justify-center border border-border',
            shouldTrigger && 'bg-primary'
          )}
        >
          <RefreshCw
            className={cn(
              'w-5 h-5 transition-all',
              isRefreshing && 'animate-spin',
              shouldTrigger ? 'text-primary-foreground' : 'text-muted-foreground'
            )}
            style={{
              transform: !isRefreshing ? `rotate(${progress * 180}deg)` : undefined
            }}
          />
        </div>
      </div>

      {/* Content */}
      <div
        className="transition-transform duration-200 ease-out"
        style={{
          transform: pullDistance > 0 ? `translateY(${pullDistance}px)` : undefined,
          transitionDuration: isPulling.current ? '0ms' : '200ms'
        }}
      >
        {children}
      </div>
    </div>
  )
}
