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

function CandidateCardSkeleton() {
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

