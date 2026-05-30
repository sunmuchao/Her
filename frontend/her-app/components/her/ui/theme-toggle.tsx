'use client'

import { useTheme } from '@/components/theme-provider'
import { Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ThemeToggleProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

export function ThemeToggle({ className, size = 'md' }: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme()

  const sizeClasses = {
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12'
  }

  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6'
  }

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
  }

  return (
    <button
      onClick={toggleTheme}
      className={cn(
        'rounded-full flex items-center justify-center transition-colors',
        'bg-secondary hover:bg-secondary/80',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
        sizeClasses[size],
        className
      )}
      aria-label={`切换到${resolvedTheme === 'dark' ? '浅色' : '深色'}模式`}
    >
      {resolvedTheme === 'dark' ? (
        <Sun className={cn(iconSizes[size], 'text-foreground')} />
      ) : (
        <Moon className={cn(iconSizes[size], 'text-foreground')} />
      )}
    </button>
  )
}
