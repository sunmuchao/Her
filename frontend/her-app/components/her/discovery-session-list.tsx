'use client'

import { useState, useEffect, useCallback } from 'react'
import { History, MessageCircle, X, ChevronRight, Sparkles, Users } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getProfileId } from '@/lib/auth/session'
import { fetchDiscoverySessionList } from '@/lib/api/endpoints/discovery'
import type { DiscoverySessionSummary } from '@/lib/types/discovery'
import { notifyError } from '@/lib/notify'
import { formatRelativeTime } from '@/lib/format-relative-time'  // ✅ 导入统一的时间格式化函数

interface DiscoverySessionListProps {
  currentSessionId: string | null
  onSelectSession: (sessionId: string) => void
  onCreateNewSession: () => void
  onClose: () => void
}

export function DiscoverySessionList({
  currentSessionId,
  onSelectSession,
  onCreateNewSession,
  onClose,
}: DiscoverySessionListProps) {
  const [sessions, setSessions] = useState<DiscoverySessionSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isClosing, setIsClosing] = useState(false)

  const handleClose = useCallback(() => {
    setIsClosing(true)
    window.setTimeout(onClose, 200)
  }, [onClose])

  useEffect(() => {
    async function loadSessions() {
      const profileId = getProfileId()
      if (!profileId) {
        setIsLoading(false)
        return
      }
      try {
        const response = await fetchDiscoverySessionList({ profileId, limit: 20 })
        setSessions(response.sessions || [])
      } catch (error) {
        notifyError(error, '加载会话历史失败')
      } finally {
        setIsLoading(false)
      }
    }
    loadSessions()
  }, [])

  // Lock body scroll and close on Escape
  useEffect(() => {
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [handleClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="会话历史"
      onClick={handleClose}
      className={cn(
        'fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm',
        isClosing ? 'animate-out fade-out duration-200' : 'animate-in fade-in duration-200',
      )}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          'relative w-full max-w-md flex flex-col max-h-[calc(85vh-3.5rem-env(safe-area-inset-bottom))] overflow-hidden',
          'rounded-t-3xl border-x border-t border-border/60 bg-card shadow-2xl mb-[calc(3.5rem+env(safe-area-inset-bottom))]',
          isClosing
            ? 'animate-out slide-out-to-bottom duration-200'
            : 'animate-in slide-in-from-bottom duration-300',
        )}
      >
        {/* Grab handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="h-1.5 w-12 rounded-full bg-border" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 pb-4 pt-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <History className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold leading-tight text-card-foreground">会话历史</h3>
              <p className="text-xs text-muted-foreground">
                {isLoading ? '加载中…' : `共 ${sessions.length} 个会话`}
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            aria-label="关闭"
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-card-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-3 pb-2">
          {isLoading ? (
            <div className="space-y-2 px-2 py-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex items-center gap-3 rounded-2xl p-3">
                  <div className="h-11 w-11 shrink-0 animate-pulse rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3.5 w-1/3 animate-pulse rounded-full bg-muted" />
                    <div className="h-3 w-2/3 animate-pulse rounded-full bg-muted/70" />
                  </div>
                </div>
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                <Sparkles className="h-7 w-7 text-primary" />
              </div>
              <p className="mb-1 font-medium text-card-foreground">还没有历史会话</p>
              <p className="text-sm text-muted-foreground">开启一次新对话，找到你的心动对象</p>
            </div>
          ) : (
            <div className="space-y-1.5 py-1">
              {sessions.map((session, index) => {
                const isActive = session.session_id === currentSessionId
                const isDone = session.phase === 'results_shown'
                return (
                  <button
                    key={session.session_id}
                    onClick={() => {
                      onSelectSession(session.session_id!)
                      handleClose()
                    }}
                    style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
                    className={cn(
                      'group flex w-full items-center gap-3 rounded-2xl p-3 text-left transition-all',
                      'animate-in fade-in slide-in-from-bottom-2 fill-mode-both duration-300',
                      isActive
                        ? 'bg-primary/10 ring-1 ring-inset ring-primary/30'
                        : 'hover:bg-muted active:scale-[0.99]',
                    )}
                  >
                    {/* Icon */}
                    <div
                      className={cn(
                        'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors',
                        isActive ? 'bg-primary/20' : 'bg-muted group-hover:bg-background',
                      )}
                    >
                      <MessageCircle
                        className={cn('h-5 w-5', isActive ? 'text-primary' : 'text-muted-foreground')}
                      />
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <div className="mb-0.5 flex items-center gap-2">
                        <span
                          className={cn(
                            'truncate text-sm font-medium',
                            isActive ? 'text-primary' : 'text-card-foreground',
                          )}
                        >
                          {isDone ? '已推荐候选人' : '正在沟通偏好'}
                        </span>
                        {isActive && (
                          <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-[10px] font-medium leading-none text-primary-foreground">
                            当前
                          </span>
                        )}
                      </div>
                      <p className="truncate text-xs text-muted-foreground">
                        {session.last_message_preview || '开始新对话'}
                      </p>
                      <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span>{formatRelativeTime(session.updated_at)}</span>
                        {session.candidate_count && session.candidate_count > 0 ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-rose-soft px-2 py-0.5 text-rose">
                            <Users className="h-3 w-3" />
                            {session.candidate_count} 人
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Arrow */}
                    <ChevronRight
                      className={cn(
                        'h-5 w-5 shrink-0 text-muted-foreground transition-transform',
                        'group-hover:translate-x-0.5 group-hover:text-card-foreground',
                      )}
                    />
                  </button>
                )
              })}
            </div>
          )}
        </div>

              </div>
    </div>
  )
}
