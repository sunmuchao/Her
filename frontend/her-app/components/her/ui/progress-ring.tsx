'use client'

import { cn } from '@/lib/utils'

interface ProgressRingProps {
  progress: number // 0-100
  size?: number
  strokeWidth?: number
  className?: string
  showPercentage?: boolean
  color?: 'primary' | 'rose' | 'gold' | 'success'
  children?: React.ReactNode
}

export function ProgressRing({
  progress,
  size = 64,
  strokeWidth = 4,
  className,
  showPercentage = false,
  color = 'primary',
  children
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (progress / 100) * circumference

  const colorClasses = {
    primary: 'text-primary',
    rose: 'text-rose',
    gold: 'text-gold',
    success: 'text-green-500'
  }

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-secondary"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn('transition-all duration-500 ease-out', colorClasses[color])}
        />
      </svg>
      {/* Center content */}
      <div className="absolute inset-0 flex items-center justify-center">
        {children ?? (showPercentage && (
          <span className="text-sm font-medium text-foreground">
            {Math.round(progress)}%
          </span>
        ))}
      </div>
    </div>
  )
}
