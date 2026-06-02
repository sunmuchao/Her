/**
 * 价值观拍卖会骨架屏
 */

import { cn } from '@/lib/utils'

export function ValuesAuctionSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-pulse">
      {/* Icon skeleton */}
      <div className="flex justify-center mb-5">
        <div className="w-20 h-20 rounded-full bg-secondary" />
      </div>

      {/* Title skeleton */}
      <div className="space-y-2 mb-5">
        <div className="h-6 bg-secondary rounded-lg w-2/3 mx-auto" />
        <div className="h-4 bg-secondary rounded-lg w-4/5 mx-auto" />
      </div>

      {/* Info cards skeleton */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
            <div className="w-10 h-10 rounded-xl bg-secondary" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 bg-secondary rounded w-12" />
              <div className="h-4 bg-secondary rounded w-16" />
            </div>
          </div>
        ))}
      </div>

      {/* Rules skeleton */}
      <div className="rounded-2xl bg-secondary/40 p-4 mb-5">
        <div className="h-4 bg-secondary rounded w-4/5 mx-auto mb-2" />
        <div className="h-4 bg-secondary rounded w-3/5 mx-auto" />
      </div>

      {/* Button skeleton */}
      <div className="h-12 bg-secondary rounded-xl" />
    </div>
  )
}

export function ValuesAuctionBiddingSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-pulse">
      {/* Header */}
      <div className="mb-4 space-y-3">
        <div className="h-6 bg-secondary rounded w-1/2 mx-auto" />
        <div className="h-8 bg-secondary rounded-full w-32 mx-auto" />
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-secondary rounded-full mb-4" />

      {/* Lots */}
      <div className="space-y-4">
        {Array.from({ length: 2 }).map((_, groupIndex) => (
          <div key={groupIndex} className="rounded-2xl bg-secondary/40 p-3">
            <div className="h-4 bg-secondary rounded w-20 mb-3" />
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="rounded-xl bg-background p-3 border border-border">
                  <div className="flex items-center justify-between">
                    <div className="h-4 bg-secondary rounded w-24" />
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-secondary" />
                      <div className="w-12 h-4 bg-secondary rounded" />
                      <div className="w-7 h-7 rounded-full bg-secondary" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Submit button */}
      <div className="h-12 bg-secondary rounded-xl mt-4" />
    </div>
  )
}

export function ValuesAuctionResultSkeleton() {
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-pulse">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="w-16 h-16 rounded-full bg-secondary mx-auto mb-3" />
        <div className="h-6 bg-secondary rounded w-32 mx-auto" />
      </div>

      {/* Top 3 */}
      <div className="rounded-2xl bg-secondary/40 p-4 mb-5">
        <div className="h-4 bg-secondary rounded w-28 mb-3" />
        <div className="space-y-2.5">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-xl bg-background p-3 border border-border">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-secondary" />
                <div className="flex-1">
                  <div className="h-4 bg-secondary rounded w-24 mb-1" />
                  <div className="h-3 bg-secondary rounded w-32" />
                </div>
                <div className="w-8 h-8 bg-secondary rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hidden values */}
      <div className="rounded-2xl bg-secondary/40 p-4 mb-5">
        <div className="h-4 bg-secondary rounded w-24 mb-3" />
        <div className="space-y-2.5">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2.5">
              <div className="w-20 h-4 bg-secondary rounded" />
              <div className="flex-1 h-2 bg-secondary rounded-full" />
              <div className="w-10 h-4 bg-secondary rounded" />
            </div>
          ))}
        </div>
      </div>

      {/* Buttons */}
      <div className="space-y-2.5">
        <div className="h-12 bg-secondary rounded-xl" />
        <div className="flex gap-2.5">
          <div className="flex-1 h-11 bg-secondary rounded-xl" />
          <div className="flex-1 h-11 bg-secondary rounded-xl" />
        </div>
      </div>
    </div>
  )
}
