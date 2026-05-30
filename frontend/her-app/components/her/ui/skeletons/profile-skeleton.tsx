import { Shimmer } from '@/components/her/ui/skeletons'
import { cn } from '@/lib/utils'

export function ProfilePageSkeleton() {
  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-medium">我的</h1>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-secondary" />
            <div className="w-8 h-8 rounded-full bg-secondary" />
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* Profile Card */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-16 h-16 rounded-full overflow-hidden">
              <Shimmer className="w-full h-full" />
            </div>
            <div className="flex-1">
              <div className="h-5 w-24 rounded bg-secondary mb-2">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-4 w-32 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>
          </div>
          <div className="h-4 w-full rounded bg-secondary mb-3">
            <Shimmer className="w-full h-full" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="px-2 py-1 bg-secondary rounded-md h-5 w-16">
                <Shimmer className="w-full h-full" />
              </div>
            ))}
          </div>
        </section>

        {/* Trust Center */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
              <Shimmer className="w-full h-full" />
            </div>
            <div className="flex-1">
              <div className="h-5 w-20 rounded bg-secondary mb-2">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-4 w-32 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>
            <div className="w-5 h-5 rounded bg-secondary" />
          </div>
          <div className="grid grid-cols-4 gap-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="text-center p-2 rounded-lg bg-secondary">
                <div className="w-5 h-5 mx-auto mb-1 rounded-full">
                  <Shimmer className="w-full h-full" />
                </div>
                <div className="h-3 w-8 mx-auto rounded bg-secondary">
                  <Shimmer className="w-full h-full" />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Action Items */}
        <section className="bg-card border border-border rounded-xl overflow-hidden">
          {[1, 2].map((i) => (
            <div
              key={i}
              className={cn(
                'px-4 py-3 flex items-center gap-3',
                i !== 2 && 'border-b border-border',
              )}
            >
              <div className="w-5 h-5 rounded bg-secondary" />
              <div className="flex-1 h-4 w-20 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="w-4 h-4 rounded bg-secondary" />
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}