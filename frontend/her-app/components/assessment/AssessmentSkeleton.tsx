'use client'

import { cn } from '@/lib/utils'

function Shimmer({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-lg bg-secondary', className)}>
      <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
    </div>
  )
}

export function AssessmentSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-pulse-soft">
      {/* Progress bar skeleton */}
      <div className="mb-4 space-y-3">
        <div className="flex items-center justify-between">
          <Shimmer className="h-4 w-20" />
          <Shimmer className="h-4 w-10" />
        </div>
        <Shimmer className="h-2 w-full rounded-full" />
      </div>
      
      {/* Question text skeleton */}
      <div className="space-y-2">
        <Shimmer className="h-6 w-full" />
        <Shimmer className="h-6 w-3/4" />
      </div>
      
      {/* Options skeleton */}
      <div className="mt-4 grid gap-2">
        {[1, 2, 3, 4, 5].map((i) => (
          <Shimmer key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    </div>
  )
}

export function AssessmentIntroSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-pulse-soft">
      {/* Icon skeleton */}
      <div className="flex justify-center mb-4">
        <Shimmer className="h-20 w-20 rounded-full" />
      </div>
      
      {/* Title and description */}
      <div className="space-y-2 text-center">
        <Shimmer className="h-7 w-48 mx-auto" />
        <Shimmer className="h-4 w-64 mx-auto" />
        <Shimmer className="h-4 w-56 mx-auto" />
      </div>
      
      {/* Info box */}
      <Shimmer className="mt-4 h-20 w-full rounded-2xl" />
      
      {/* Button */}
      <Shimmer className="mt-4 h-11 w-full rounded-lg" />
    </div>
  )
}

export function AssessmentResultSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-pulse-soft">
      {/* Type code */}
      <Shimmer className="h-4 w-16 mb-2" />
      <Shimmer className="h-8 w-24 mb-4" />
      
      {/* Radar chart placeholder */}
      <div className="flex justify-center my-6">
        <Shimmer className="h-48 w-48 rounded-full" />
      </div>
      
      {/* Labels */}
      <div className="flex flex-wrap gap-2 mb-4">
        {[1, 2, 3, 4].map((i) => (
          <Shimmer key={i} className="h-8 w-20 rounded-full" />
        ))}
      </div>
      
      {/* Dimension bars */}
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i}>
            <div className="flex justify-between mb-1">
              <Shimmer className="h-4 w-24" />
              <Shimmer className="h-4 w-10" />
            </div>
            <Shimmer className="h-2 w-full rounded-full" />
          </div>
        ))}
      </div>
    </div>
  )
}
