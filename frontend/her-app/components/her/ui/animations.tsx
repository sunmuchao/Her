'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface FadeInProps {
  children: ReactNode
  className?: string
  delay?: number
  duration?: number
  direction?: 'up' | 'down' | 'left' | 'right' | 'none'
  distance?: number
}

export function FadeIn({
  children,
  className,
  delay = 0,
  duration = 400,
  direction = 'up',
  distance = 20,
}: FadeInProps) {
  const [isVisible, setIsVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.1, rootMargin: '50px' },
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [])

  const getTransform = () => {
    if (direction === 'none') return 'translate(0, 0)'
    const transforms = {
      up: `translateY(${distance}px)`,
      down: `translateY(-${distance}px)`,
      left: `translateX(${distance}px)`,
      right: `translateX(-${distance}px)`,
    }
    return transforms[direction]
  }

  return (
    <div
      ref={ref}
      className={cn('transition-all', className)}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translate(0, 0)' : getTransform(),
        transitionDuration: `${duration}ms`,
        transitionDelay: `${delay}ms`,
        transitionTimingFunction: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)',
      }}
    >
      {children}
    </div>
  )
}

interface PageTransitionProps {
  children: ReactNode
  className?: string
}

export function PageTransition({ children, className }: PageTransitionProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div
      className={cn(
        'transition-all duration-300',
        mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2',
        className,
      )}
    >
      {children}
    </div>
  )
}

interface HeartbeatProps {
  children: ReactNode
  className?: string
  active?: boolean
}

export function Heartbeat({ children, className, active = true }: HeartbeatProps) {
  return (
    <div className={cn(active && 'animate-heartbeat', className)}>
      {children}
    </div>
  )
}

interface OnlineIndicatorProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function OnlineIndicator({ className, size = 'md' }: OnlineIndicatorProps) {
  const sizeClasses = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4',
  }

  return (
    <span className={cn('relative flex', sizeClasses[size], className)}>
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
      <span className={cn('relative inline-flex rounded-full bg-green-500', sizeClasses[size])} />
    </span>
  )
}
