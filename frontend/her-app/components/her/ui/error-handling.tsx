'use client'

import { AlertCircle, RefreshCw, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface PageErrorStateProps {
  /** 错误信息 */
  message: string
  /** 错误标题 */
  title?: string
  /** 显示模式：full（全屏）或 inline（内嵌） */
  variant?: 'full' | 'inline'
  /** 重试回调 */
  onRetry?: () => void
  /** 返回回调 */
  onBack?: () => void
  /** 自定义样式 */
  className?: string
}

/**
 * 统一的页面错误状态组件
 *
 * 使用规范：
 * - 页面级错误（如数据加载失败）：使用 variant='full'
 * - 模块级错误（如某个卡片数据失败）：使用 variant='inline'
 */
export function PageErrorState({
  message,
  title = '加载失败',
  variant = 'full',
  onRetry,
  onBack,
  className,
}: PageErrorStateProps) {
  if (variant === 'inline') {
    return (
      <section
        className={cn(
          'bg-gold/10 border border-gold/30 rounded-xl p-3',
          className,
        )}
        role="alert"
      >
        <div className="flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-gold shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-gold font-medium">{title}</p>
            <p className="text-xs text-gold/80 mt-0.5">{message}</p>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="text-xs text-gold underline hover:no-underline"
              aria-label="重试"
            >
              重试
            </button>
          )}
        </div>
      </section>
    )
  }

  // full 模式：全屏错误状态
  return (
    <div
      className={cn(
        'flex flex-col h-full items-center justify-center gap-3 px-6 py-12 text-center',
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
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/80 transition-colors"
          >
            返回
          </button>
        )}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="重试加载"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors focus-ring"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            重试
          </button>
        )}
      </div>
    </div>
  )
}