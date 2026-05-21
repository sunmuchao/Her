'use client'

import { cn } from '@/lib/utils'

// Base shimmer skeleton
function Shimmer({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-secondary rounded', className)}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent" />
    </div>
  )
}

export function CandidateCardSkeleton() {
  return (
    <div className="w-48 shrink-0 bg-card border border-border rounded-xl overflow-hidden">
      <Shimmer className="h-56 rounded-none" />
      <div className="p-3 space-y-2">
        <Shimmer className="h-4 w-16" />
        <Shimmer className="h-3 w-24" />
      </div>
    </div>
  )
}

export function InboxItemSkeleton() {
  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <div className="flex gap-3">
        <Shimmer className="w-14 h-14 rounded-lg shrink-0" />
        <div className="flex-1 space-y-2 py-1">
          <Shimmer className="h-4 w-20" />
          <Shimmer className="h-3 w-32" />
          <Shimmer className="h-3 w-full" />
        </div>
      </div>
    </div>
  )
}

export function ChatMessageSkeleton({ isSent = false }: { isSent?: boolean }) {
  return (
    <div className={cn('flex', isSent ? 'justify-end' : 'justify-start')}>
      <div className="max-w-[75%]">
        <div className={cn(
          'px-4 py-3 rounded-2xl',
          isSent ? 'bg-primary/20' : 'bg-secondary'
        )}>
          <div className="space-y-1.5">
            <Shimmer className={cn('h-3', isSent ? 'w-28' : 'w-32')} />
            <Shimmer className={cn('h-3', isSent ? 'w-20' : 'w-24')} />
          </div>
        </div>
      </div>
    </div>
  )
}

export function ProfileHeroSkeleton() {
  return (
    <div className="relative h-[400px] bg-secondary">
      <Shimmer className="absolute inset-0 rounded-none" />
      <div className="absolute top-12 left-4">
        <Shimmer className="w-10 h-10 rounded-full" />
      </div>
      <div className="absolute bottom-6 left-5 space-y-2">
        <Shimmer className="h-8 w-24" />
        <Shimmer className="h-4 w-40" />
      </div>
    </div>
  )
}

export function PageLoadingSkeleton() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      <p className="text-sm text-muted-foreground">加载中...</p>
    </div>
  )
}

// New enhanced skeletons

export function DiscoverPageSkeleton() {
  return (
    <div className="min-h-screen bg-background p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <Shimmer className="h-8 w-24" />
        <Shimmer className="h-8 w-8 rounded-full" />
      </div>
      
      {/* AI Assistant Card */}
      <div className="bg-card rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-3">
          <Shimmer className="w-12 h-12 rounded-full" />
          <div className="flex-1 space-y-2">
            <Shimmer className="h-4 w-20" />
            <Shimmer className="h-3 w-32" />
          </div>
        </div>
        <Shimmer className="h-20 w-full rounded-lg" />
      </div>

      {/* Preference Tags */}
      <div className="flex gap-2 overflow-hidden">
        {[1, 2, 3, 4].map((i) => (
          <Shimmer key={i} className="h-8 w-20 rounded-full shrink-0" />
        ))}
      </div>

      {/* Candidate Cards */}
      <div className="flex gap-3 overflow-hidden">
        {[1, 2, 3].map((i) => (
          <CandidateCardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

export function RelationshipsPageSkeleton() {
  return (
    <div className="min-h-screen bg-background p-4 space-y-4">
      {/* Header */}
      <Shimmer className="h-8 w-32 mb-4" />
      
      {/* Tab bar */}
      <div className="flex gap-4 mb-4">
        <Shimmer className="h-10 w-24 rounded-lg" />
        <Shimmer className="h-10 w-24 rounded-lg" />
        <Shimmer className="h-10 w-24 rounded-lg" />
      </div>

      {/* List items */}
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <InboxItemSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

export function ProfilePageSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      {/* Avatar section */}
      <div className="flex flex-col items-center py-8 space-y-4">
        <Shimmer className="w-24 h-24 rounded-full" />
        <Shimmer className="h-6 w-32" />
        <Shimmer className="h-4 w-48" />
      </div>

      {/* Stats */}
      <div className="flex justify-center gap-8 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex flex-col items-center gap-1">
            <Shimmer className="h-6 w-8" />
            <Shimmer className="h-3 w-12" />
          </div>
        ))}
      </div>

      {/* Menu items */}
      <div className="px-4 space-y-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Shimmer key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    </div>
  )
}

export function CandidateDetailSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      {/* Image carousel */}
      <Shimmer className="h-[400px] w-full rounded-none" />
      
      {/* Content */}
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Shimmer className="h-7 w-24" />
            <Shimmer className="h-4 w-40" />
          </div>
          <Shimmer className="w-12 h-12 rounded-full" />
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4].map((i) => (
            <Shimmer key={i} className="h-7 w-16 rounded-full" />
          ))}
        </div>

        {/* Bio */}
        <div className="space-y-2">
          <Shimmer className="h-4 w-full" />
          <Shimmer className="h-4 w-full" />
          <Shimmer className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  )
}

export function ChatPageSkeleton() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 border-b border-border">
        <Shimmer className="w-10 h-10 rounded-full" />
        <div className="flex-1 space-y-1">
          <Shimmer className="h-5 w-24" />
          <Shimmer className="h-3 w-16" />
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 p-4 space-y-4">
        <ChatMessageSkeleton isSent={false} />
        <ChatMessageSkeleton isSent={true} />
        <ChatMessageSkeleton isSent={false} />
        <ChatMessageSkeleton isSent={true} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border">
        <Shimmer className="h-12 w-full rounded-full" />
      </div>
    </div>
  )
}
