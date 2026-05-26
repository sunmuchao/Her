'use client'

import { ReactNode, useEffect, useState } from 'react'

interface PageTransitionProps {
  children: ReactNode
  className?: string
}

export function PageTransition({ children, className = '' }: PageTransitionProps) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    // Small delay to ensure transition fires
    const timer = requestAnimationFrame(() => {
      setIsVisible(true)
    })
    return () => cancelAnimationFrame(timer)
  }, [])

  return (
    <div 
      className={`transition-all duration-300 ease-out ${
        isVisible 
          ? 'opacity-100 translate-y-0' 
          : 'opacity-0 translate-y-2'
      } ${className}`}
    >
      {children}
    </div>
  )
}

// Slide-in transition for detail pages
export function SlideInTransition({ children, className = '', direction = 'right' }: PageTransitionProps & { direction?: 'left' | 'right' | 'up' | 'down' }) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const timer = requestAnimationFrame(() => {
      setIsVisible(true)
    })
    return () => cancelAnimationFrame(timer)
  }, [])

  const directionClasses = {
    left: isVisible ? 'translate-x-0' : '-translate-x-4',
    right: isVisible ? 'translate-x-0' : 'translate-x-4',
    up: isVisible ? 'translate-y-0' : '-translate-y-4',
    down: isVisible ? 'translate-y-0' : 'translate-y-4',
  }

  return (
    <div 
      className={`transition-all duration-300 ease-out ${
        isVisible ? 'opacity-100' : 'opacity-0'
      } ${directionClasses[direction]} ${className}`}
    >
      {children}
    </div>
  )
}
