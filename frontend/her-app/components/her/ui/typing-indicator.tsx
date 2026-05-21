'use client'

import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'

export function TypingIndicator({ name = '小雅' }: { name?: string }) {
  return (
    <div className="flex justify-start items-end gap-2">
      <XiaoyaAvatar size={28} />
      <div className="bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{name}正在输入</span>
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <span key={i} className="w-1.5 h-1.5 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function ChatTypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span key={i} className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
          ))}
        </div>
      </div>
    </div>
  )
}
