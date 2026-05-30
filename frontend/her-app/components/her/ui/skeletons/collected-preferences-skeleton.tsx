import { ArrowLeft } from 'lucide-react'
import { Shimmer } from '@/components/her/ui/skeletons'
import { cn } from '@/lib/utils'

interface CollectedPreferencesSkeletonProps {
  onBack?: () => void
}

/**
 * 已收集偏好页面骨架屏
 */
export function CollectedPreferencesSkeleton({ onBack }: CollectedPreferencesSkeletonProps) {
  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="w-8 h-8 flex items-center justify-center focus-ring rounded-full"
            aria-label="返回"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="h-5 w-24 rounded bg-secondary mb-1">
              <Shimmer className="w-full h-full" />
            </div>
            <div className="h-3 w-32 rounded bg-secondary">
              <Shimmer className="w-full h-full" />
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 pb-20">
        {[1, 2, 3, 4].map((i) => (
          <section
            key={i}
            className="bg-card border border-border rounded-xl p-4 space-y-2"
          >
            {/* 标题行 */}
            <div className="flex items-start justify-between gap-2">
              <div className="h-4 w-20 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-4 w-16 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>

            {/* 来源行 */}
            <div className="flex gap-3">
              <div className="h-3 w-20 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-3 w-16 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>

            {/* 证据行 */}
            <div className="h-3 w-full rounded bg-secondary">
              <Shimmer className="w-full h-full" />
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}