'use client'

export function CandidateCardSkeleton() {
  return (
    <div className="w-48 shrink-0 bg-card border border-border rounded-xl overflow-hidden animate-pulse">
      <div className="h-56 bg-secondary" />
      <div className="p-3 space-y-2">
        <div className="h-4 w-16 bg-secondary rounded" />
        <div className="h-3 w-24 bg-secondary rounded" />
      </div>
    </div>
  )
}

export function InboxItemSkeleton() {
  return (
    <div className="bg-card border border-border rounded-xl p-3 animate-pulse">
      <div className="flex gap-3">
        <div className="w-14 h-14 bg-secondary rounded-lg shrink-0" />
        <div className="flex-1 space-y-2 py-1">
          <div className="h-4 w-20 bg-secondary rounded" />
          <div className="h-3 w-32 bg-secondary rounded" />
          <div className="h-3 w-full bg-secondary rounded" />
        </div>
      </div>
    </div>
  )
}

export function ChatMessageSkeleton({ isSent = false }: { isSent?: boolean }) {
  return (
    <div className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[75%] animate-pulse">
        <div className={`px-4 py-3 rounded-2xl ${isSent ? 'bg-primary/20' : 'bg-secondary'}`}>
          <div className="space-y-1.5">
            <div className={`h-3 ${isSent ? 'w-28' : 'w-32'} bg-current opacity-20 rounded`} />
            <div className={`h-3 ${isSent ? 'w-20' : 'w-24'} bg-current opacity-20 rounded`} />
          </div>
        </div>
      </div>
    </div>
  )
}

export function ProfileHeroSkeleton() {
  return (
    <div className="h-[400px] bg-secondary animate-pulse">
      <div className="absolute top-12 left-4 w-10 h-10 rounded-full bg-black/20" />
      <div className="absolute bottom-6 left-5 space-y-2">
        <div className="h-8 w-24 bg-white/20 rounded" />
        <div className="h-4 w-40 bg-white/10 rounded" />
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
