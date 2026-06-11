'use client'

import { useState, useEffect } from 'react'
import { History, Plus, MessageCircle, X, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getProfileId } from '@/lib/auth/session'
import { fetchDiscoverySessionList } from '@/lib/api/endpoints/discovery'
import type { DiscoverySessionSummary } from '@/lib/types/discovery'
import { notifyError } from '@/lib/notify'

interface DiscoverySessionListProps {
  currentSessionId: string | null
  onSelectSession: (sessionId: string) => void
  onCreateNewSession: () => void
  onClose: () => void
}

function formatRelativeTime(dateStr: string | undefined): string {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins} 分钟前`
    if (diffHours < 24) return `${diffHours} 小时前`
    if (diffDays < 7) return `${diffDays} 天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

export function DiscoverySessionList({
  currentSessionId,
  onSelectSession,
  onCreateNewSession,
  onClose,
}: DiscoverySessionListProps) {
  const [sessions, setSessions] = useState<DiscoverySessionSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)

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

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end justify-center">
      <div className="bg-background w-full max-w-md rounded-t-2xl shadow-xl max-h-[80vh] flex flex-col animate-in slide-in-from-bottom duration-300">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-muted-foreground" />
            <h3 className="font-semibold text-foreground">会话历史</h3>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-muted transition-colors"
          >
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <MessageCircle className="w-12 h-12 mb-3 opacity-50" />
              <p className="text-sm">还没有历史会话</p>
            </div>
          ) : (
            <div className="space-y-1">
              {sessions.map((session) => (
                <button
                  key={session.session_id}
                  onClick={() => {
                    onSelectSession(session.session_id!)
                    onClose()
                  }}
                  className={cn(
                    'w-full flex items-center gap-3 p-3 rounded-lg transition-colors text-left',
                    session.session_id === currentSessionId
                      ? 'bg-primary/10 border border-primary/20'
                      : 'hover:bg-muted',
                  )}
                >
                  {/* Icon */}
                  <div className={cn(
                    'w-10 h-10 rounded-full flex items-center justify-center',
                    session.session_id === currentSessionId
                      ? 'bg-primary/20'
                      : 'bg-muted',
                  )}>
                    <MessageCircle className={cn(
                      'w-5 h-5',
                      session.session_id === currentSessionId
                        ? 'text-primary'
                        : 'text-muted-foreground',
                    )} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cn(
                        'text-sm font-medium',
                        session.session_id === currentSessionId
                          ? 'text-primary'
                          : 'text-foreground',
                      )}>
                        {session.phase === 'results_shown' ? '已推荐候选人' : '正在沟通偏好'}
                      </span>
                      {session.session_id === currentSessionId && (
                        <span className="text-xs bg-primary text-primary-foreground px-2 py-0.5 rounded-full">
                          当前
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {session.last_message_preview || '开始新对话'}
                    </p>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      <span>{formatRelativeTime(session.updated_at)}</span>
                      {session.candidate_count && session.candidate_count > 0 && (
                        <span className="text-rose-soft">推荐 {session.candidate_count} 人</span>
                      )}
                    </div>
                  </div>

                  {/* Arrow */}
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t">
          <button
            onClick={() => {
              onCreateNewSession()
              onClose()
            }}
            className="w-full flex items-center justify-center gap-2 py-3 bg-primary text-primary-foreground rounded-full font-medium text-sm hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-5 h-5" />
            <span>新建会话</span>
          </button>
        </div>
      </div>
    </div>
  )
}