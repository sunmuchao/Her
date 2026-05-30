import { Shimmer } from '@/components/her/ui/skeletons'
import { cn } from '@/lib/utils'

export function TrustCenterPageSkeleton() {
  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
              <Shimmer className="w-full h-full" />
            </div>
            <div>
              <div className="h-5 w-20 rounded bg-secondary mb-2">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-4 w-32 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* Summary Card */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
              <Shimmer className="w-full h-full" />
            </div>
            <div>
              <div className="h-5 w-24 rounded bg-secondary mb-2">
                <Shimmer className="w-full h-full" />
              </div>
              <div className="h-4 w-40 rounded bg-secondary">
                <Shimmer className="w-full h-full" />
              </div>
            </div>
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

        {/* Verification Status */}
        <section>
          <div className="h-4 w-20 rounded bg-secondary mb-2 ml-1">
            <Shimmer className="w-full h-full" />
          </div>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className={cn(
                  'px-4 py-3 flex items-center gap-3',
                  i !== 3 && 'border-b border-border',
                )}
              >
                <div className="w-5 h-5 rounded-full bg-secondary" />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="h-4 w-16 rounded bg-secondary">
                      <Shimmer className="w-full h-full" />
                    </div>
                    <div className="h-3 w-10 rounded bg-secondary" />
                  </div>
                  <div className="h-3 w-24 rounded bg-secondary">
                    <Shimmer className="w-full h-full" />
                  </div>
                </div>
                <div className="w-4 h-4 rounded bg-secondary" />
              </div>
            ))}
          </div>
        </section>

        {/* Contact Support */}
        <div className="bg-secondary rounded-xl p-4 text-center">
          <div className="h-4 w-24 mx-auto rounded bg-secondary mb-1">
            <Shimmer className="w-full h-full" />
          </div>
          <div className="h-5 w-20 mx-auto rounded bg-secondary">
            <Shimmer className="w-full h-full" />
          </div>
        </div>
      </div>
    </div>
  )
}