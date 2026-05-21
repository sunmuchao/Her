'use client'

import { useEffect, useRef, useState, type ReactNode, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

// FadeIn animation component
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
  distance = 20
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
      { threshold: 0.1, rootMargin: '50px' }
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
      right: `translateX(-${distance}px)`
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
        transitionTimingFunction: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)'
      }}
    >
      {children}
    </div>
  )
}

// Slide up animation (simpler version)
interface SlideUpProps {
  children: ReactNode
  className?: string
  delay?: number
  show?: boolean
}

export function SlideUp({ children, className, delay = 0, show = true }: SlideUpProps) {
  return (
    <div
      className={cn(
        'transition-all duration-500',
        show ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4',
        className
      )}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// Stagger container for list animations
interface StaggerContainerProps {
  children: ReactNode
  className?: string
  staggerDelay?: number
  initialDelay?: number
}

export function StaggerContainer({ 
  children, 
  className,
  staggerDelay = 50,
  initialDelay = 0
}: StaggerContainerProps) {
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
      { threshold: 0.1 }
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className={className}>
      {Array.isArray(children) ? children.map((child, index) => (
        <div
          key={index}
          className="transition-all duration-400"
          style={{
            opacity: isVisible ? 1 : 0,
            transform: isVisible ? 'translateY(0)' : 'translateY(16px)',
            transitionDelay: `${initialDelay + index * staggerDelay}ms`,
            transitionTimingFunction: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)'
          }}
        >
          {child}
        </div>
      )) : children}
    </div>
  )
}

// Scale animation on interaction
interface ScaleOnPressProps {
  children: ReactNode
  className?: string
  scale?: number
}

export function ScaleOnPress({ children, className, scale = 0.97 }: ScaleOnPressProps) {
  const [isPressed, setIsPressed] = useState(false)

  return (
    <div
      className={cn('transition-transform duration-150', className)}
      style={{ transform: isPressed ? `scale(${scale})` : 'scale(1)' }}
      onMouseDown={() => setIsPressed(true)}
      onMouseUp={() => setIsPressed(false)}
      onMouseLeave={() => setIsPressed(false)}
      onTouchStart={() => setIsPressed(true)}
      onTouchEnd={() => setIsPressed(false)}
    >
      {children}
    </div>
  )
}

// Pulse animation for attention
interface PulseProps {
  children: ReactNode
  className?: string
  active?: boolean
}

export function Pulse({ children, className, active = true }: PulseProps) {
  return (
    <div className={cn(active && 'animate-pulse-soft', className)}>
      {children}
    </div>
  )
}

// Shimmer effect for loading states
export function Shimmer({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-secondary rounded', className)}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent" />
    </div>
  )
}

// Page transition wrapper
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
        className
      )}
    >
      {children}
    </div>
  )
}

// Heartbeat animation for CTA buttons
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

// Typing dots animation
export function TypingDots({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      <span className="w-2 h-2 bg-current rounded-full animate-bounce-dot" style={{ animationDelay: '0ms' }} />
      <span className="w-2 h-2 bg-current rounded-full animate-bounce-dot" style={{ animationDelay: '150ms' }} />
      <span className="w-2 h-2 bg-current rounded-full animate-bounce-dot" style={{ animationDelay: '300ms' }} />
    </div>
  )
}

// Online status indicator
interface OnlineIndicatorProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function OnlineIndicator({ className, size = 'md' }: OnlineIndicatorProps) {
  const sizeClasses = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4'
  }

  return (
    <span className={cn('relative flex', sizeClasses[size], className)}>
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
      <span className={cn('relative inline-flex rounded-full bg-green-500', sizeClasses[size])} />
    </span>
  )
}
