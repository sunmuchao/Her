'use client'

import { Button } from '@/components/ui/button'
import { AlertCircle, RefreshCw, WifiOff } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AssessmentError {
  message: string
  code?: string
  retryable: boolean
}

interface AssessmentErrorCardProps {
  error: AssessmentError
  onRetry?: () => void
  onClose?: () => void
}

export function AssessmentErrorCard({ error, onRetry, onClose }: AssessmentErrorCardProps) {
  const isNetworkError = error.code === 'NETWORK_ERROR' || error.message.includes('network')
  
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Error Icon */}
      <div className="flex justify-center mb-4">
        <div className={cn(
          'flex items-center justify-center w-16 h-16 rounded-full',
          isNetworkError ? 'bg-gold-soft' : 'bg-rose-soft'
        )}>
          {isNetworkError ? (
            <WifiOff className="w-7 h-7 text-gold" />
          ) : (
            <AlertCircle className="w-7 h-7 text-rose" />
          )}
        </div>
      </div>

      {/* Error Message */}
      <div className="text-center space-y-2 mb-5">
        <h3 className="text-lg font-semibold">
          {isNetworkError ? '网络连接失败' : '出了点问题'}
        </h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {error.message}
        </p>
      </div>

      {/* Retry Button */}
      {error.retryable && onRetry && (
        <Button
          className="w-full h-11 rounded-xl mb-2"
          onClick={onRetry}
        >
          <RefreshCw className="w-4 h-4 mr-2" />
          重试
        </Button>
      )}

      {/* Close Button */}
      {onClose && (
        <Button
          variant="ghost"
          className="w-full h-11 rounded-xl"
          onClick={onClose}
        >
          关闭
        </Button>
      )}

      {/* Help Text */}
      <p className="mt-4 text-center text-xs text-muted-foreground">
        {'如果问题持续存在，请稍后再试'}
      </p>
    </div>
  )
}
