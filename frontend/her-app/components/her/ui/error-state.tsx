'use client'

import { AlertCircle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

type ErrorStateProps = {
  title?: string
  message: string
  onRetry?: () => void
  onBack?: () => void
  className?: string
}

export function ErrorState({
  title = '加载失败',
  message,
  onRetry,
  onBack,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 px-6 py-12 text-center',
        className,
      )}
      role="alert"
      aria-labelledby="error-state-title"
      aria-describedby="error-state-message"
    >
      <AlertCircle className="w-10 h-10 text-destructive" aria-hidden="true" />
      <div>
        <p id="error-state-title" className="text-sm font-medium text-foreground">
          {title}
        </p>
        <p id="error-state-message" className="text-sm text-muted-foreground mt-1">
          {message}
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-secondary text-secondary-foreground text-sm font-medium"
          >
            返回
          </button>
        )}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="重试加载"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary text-primary-foreground text-sm font-medium"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            重试
          </button>
        )}
      </div>
    </div>
  )
}
