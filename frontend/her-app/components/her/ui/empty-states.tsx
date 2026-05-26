'use client'

import { Heart, MessageCircle, Search, Users } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FadeIn, Heartbeat } from './animations'

interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <FadeIn className={cn('flex flex-col items-center justify-center py-16 px-8', className)}>
      {icon && (
        <div className="w-20 h-20 bg-gradient-to-br from-rose-soft to-gold-soft rounded-full flex items-center justify-center mb-5 shadow-sm">
          {icon}
        </div>
      )}
      <h3 className="font-semibold text-foreground text-lg mb-2 text-center">{title}</h3>
      <p className="text-sm text-muted-foreground text-center max-w-[260px] leading-relaxed mb-5">
        {description}
      </p>
      {action && (
        <Heartbeat>
          <button 
            onClick={action.onClick} 
            className="px-6 py-2.5 bg-primary text-primary-foreground rounded-full text-sm font-medium shadow-md hover:shadow-lg transition-shadow focus-ring"
          >
            {action.label}
          </button>
        </Heartbeat>
      )}
    </FadeIn>
  )
}

export function EmptyRecommendations({ onRefresh }: { onRefresh?: () => void }) {
  return (
    <EmptyState
      icon={<Heart className="w-9 h-9 text-rose" />}
      title="暂时没有新的推荐"
      description="小雅正在为你寻找合适的人选，告诉她你的期待可以加快匹配速度哦"
      action={onRefresh ? {
        label: '告诉小雅你的期待',
        onClick: onRefresh
      } : undefined}
    />
  )
}

export function EmptyConversations({ onStart }: { onStart?: () => void }) {
  return (
    <EmptyState
      icon={<MessageCircle className="w-9 h-9 text-primary" />}
      title="还没有进行中的对话"
      description="去和小雅聊聊吧，她会帮你找到合适的人，开启美好的缘分"
      action={onStart ? {
        label: '和小雅聊聊',
        onClick: onStart
      } : undefined}
    />
  )
}

export function EmptySearchResults({ keyword }: { keyword: string }) {
  return (
    <EmptyState
      icon={<Search className="w-8 h-8 text-muted-foreground" />}
      title="没有找到相关结果"
      description={`尝试其他关键词搜索，或者让小雅帮你推荐类似「${keyword}」的人选`}
    />
  )
}

export function EmptyRelationships({
  onDiscover,
  title,
  description,
}: {
  onDiscover?: () => void
  title?: string
  description?: string
}) {
  return (
    <EmptyState
      icon={<Users className="w-9 h-9 text-primary" />}
      title={title || '还没有进行中的关系'}
      description={description || '去发现页认识新朋友吧，小雅会帮你找到志同道合的人'}
      action={onDiscover ? {
        label: '去发现页',
        onClick: onDiscover
      } : undefined}
    />
  )
}

// Inline empty state for smaller spaces
export function InlineEmpty({ 
  message, 
  className 
}: { 
  message: string
  className?: string 
}) {
  return (
    <div className={cn(
      'flex items-center justify-center py-8 px-4 text-sm text-muted-foreground',
      className
    )}>
      {message}
    </div>
  )
}
