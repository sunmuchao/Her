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
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <div className="flex-shrink-0 p-4 space-y-4 border-b border-border">
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

      </div>
      <div className="flex-1 min-h-0 overflow-hidden p-4 space-y-3">
        <Shimmer className="h-16 w-[80%] rounded-2xl" />
        <Shimmer className="h-12 w-[60%] rounded-2xl ml-auto" />
        <Shimmer className="h-20 w-full rounded-2xl" />
      </div>
      <div className="flex-shrink-0 p-4 border-t border-border">
        <Shimmer className="h-11 w-full rounded-xl" />
      </div>
    </div>
  )
}

export function RelationshipsPageSkeleton() {
  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="sticky top-0 z-20 bg-background border-b border-border px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <Shimmer className="h-6 w-16" />
            <Shimmer className="h-3 w-28" />
          </div>
          <Shimmer className="h-9 w-9 rounded-full" />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* 正在进行中 section */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <Shimmer className="h-4 w-20" />
            <Shimmer className="h-3 w-8" />
          </div>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-card border border-border rounded-xl p-3">
                <div className="flex items-center gap-3">
                  <Shimmer className="w-12 h-12 rounded-full shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <Shimmer className="h-4 w-16" />
                      <Shimmer className="h-4 w-4 rounded-full" />
                      <Shimmer className="h-4 w-12 rounded-full ml-auto" />
                    </div>
                    <Shimmer className="h-3 w-32" />
                    <Shimmer className="h-2 w-16" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 牵线中 section */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <Shimmer className="h-4 w-16" />
            <Shimmer className="h-3 w-8" />
          </div>
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="bg-card border border-border rounded-xl p-3">
                <div className="flex items-center gap-3">
                  <Shimmer className="w-12 h-12 rounded-full shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <Shimmer className="h-4 w-16" />
                      <Shimmer className="h-3 w-20" />
                    </div>
                    <Shimmer className="h-3 w-24" />
                  </div>
                  <Shimmer className="h-5 w-14 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

