'use client'

import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  /** 页面标题 */
  title: string
  /** 标题下方的描述文字 */
  subtitle?: string
  /** 是否显示返回按钮 */
  showBack?: boolean
  /** 返回按钮点击回调 */
  onBack?: () => void
  /** 右侧操作区域（按钮、图标等） */
  rightActions?: ReactNode
  /** 左侧图标（替代返回按钮时使用） */
  icon?: ReactNode
  /** 自定义样式 */
  className?: string
}

/**
 * 统一的页面头部组件
 *
 * 使用规范：
 * - 主Tab页面：showBack=false，可传 rightActions
 * - 子页面/详情页：showBack=true，传 onBack
 * - 特殊页面（如信任中心）：传 icon + title + subtitle
 */
export function PageHeader({
  title,
  subtitle,
  showBack = false,
  onBack,
  rightActions,
  icon,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-20 bg-background border-b border-border safe-area-top',
        className,
      )}
    >
      <div className="px-4 py-3 flex items-center gap-3">
        {/* 左侧：返回按钮或图标 */}
        {showBack && (
          <button
            type="button"
            onClick={onBack}
            className="w-8 h-8 flex items-center justify-center focus-ring rounded-full hover:bg-secondary/50 transition-colors"
            aria-label="返回"
          >
            <ArrowLeft className="w-5 h-5" aria-hidden="true" />
          </button>
        )}
        {!showBack && icon && (
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
            {icon}
          </div>
        )}

        {/* 中间：标题 + 描述 */}
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-medium truncate">{title}</h1>
          {subtitle && (
            <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
          )}
        </div>

        {/* 右侧：操作区域 */}
        {rightActions && (
          <div className="flex items-center gap-2">{rightActions}</div>
        )}
      </div>
    </header>
  )
}