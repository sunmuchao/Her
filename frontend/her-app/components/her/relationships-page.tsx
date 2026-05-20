'use client'

import { useEffect, useState } from 'react'
import { AlertCircle, ChevronRight, Loader2, MessageCircle, ShieldCheck } from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface RelationshipsPageProps {
  runtimeContext: HerRuntimeContext
  onOpenChat: (conversationId: string) => void
  onStartVerification: () => void
}

type TimelineResponse = {
  case_id: string
  requester_id: string
  conversation_count: number
  conversations: Array<{
    conversation: {
      conversation_id: string
      display_name?: string
      conversation_key?: string
      layout_role?: string
      case_id?: string
    }
    messages: Array<{
      message_id: number
      body?: string
      created_at?: string
    }>
  }>
}

export default function RelationshipsPage({
  runtimeContext,
  onOpenChat,
  onStartVerification,
}: RelationshipsPageProps) {
  const [data, setData] = useState<TimelineResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function loadTimeline() {
      if (!runtimeContext.caseId || !runtimeContext.userId) {
        setLoading(false)
        setError('关系页需要 case_id 和 user_id 才能接入真实聊天时间线。')
        return
      }
      setLoading(true)
      setError(null)
      try {
        const payload = await gatewayJson<TimelineResponse>(
          `/v2/chat/cases/${runtimeContext.caseId}/timeline${queryString({
            requester_id: runtimeContext.userId,
          })}`,
        )
        if (!active) {
          return
        }
        setData(payload)
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '关系页时间线加载失败')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadTimeline()
    return () => {
      active = false
    }
  }, [runtimeContext.caseId, runtimeContext.userId])

  return (
    <div className="flex flex-col h-full">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <h1 className="editorial-title text-2xl text-foreground">关系</h1>
            <p className="text-xs text-muted-foreground mt-0.5">当前关系进展与对话入口</p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <section className="rounded-3xl bg-gradient-to-br from-card to-blush/20 p-5 border border-border/40 shadow-soft">
          <h2 className="text-sm font-medium text-foreground">关系状态</h2>
          <p className="mt-2 text-sm leading-6 text-taupe">
            这一页已经接到当前后端的 `case conversation timeline`。如果你传入有效的 `case_id`
            和 `user_id`，这里会展示真实会话，而不是静态 mock。
          </p>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-foreground">会话列表</h2>
            {data ? (
              <span className="text-xs text-muted-foreground">{data.conversation_count} 条会话</span>
            ) : null}
          </div>

          {loading ? (
            <div className="flex items-center justify-center rounded-2xl bg-card p-8 text-muted-foreground shadow-soft border border-border/30">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              正在读取关系时间线
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
              {error}
            </div>
          ) : (
            data?.conversations.map((entry) => {
              const lastMessage = entry.messages[entry.messages.length - 1]
              return (
                <button
                  key={entry.conversation.conversation_id}
                  onClick={() => onOpenChat(entry.conversation.conversation_id)}
                  className="w-full rounded-2xl border border-border/40 bg-card p-4 text-left shadow-soft"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-rose-soft/40">
                      <MessageCircle className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-medium text-foreground">
                          {entry.conversation.display_name || entry.conversation.layout_role || '当前会话'}
                        </h3>
                        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                          {entry.conversation.conversation_key || entry.conversation.conversation_id}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
                        {lastMessage?.body || '这条会话目前还没有消息。'}
                      </p>
                      <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary">
                        打开会话
                        <ChevronRight className="h-3.5 w-3.5" />
                      </div>
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-medium text-foreground">待处理事项</h2>
          <button
            onClick={onStartVerification}
            className="w-full rounded-2xl border border-rose-soft/40 bg-gradient-to-r from-blush/50 to-card p-4 text-left shadow-soft"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-soft/60">
                <ShieldCheck className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">完善认证与补件</p>
                <p className="text-xs text-muted-foreground mt-1">
                  进入信任与认证流程，处理资料核验、活体视频或申诉事项。
                </p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </button>
          {!runtimeContext.caseId ? (
            <div className="rounded-2xl bg-secondary/60 p-4 text-xs text-muted-foreground flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              如果要联调真实关系页，请在 URL 或 `.env.local` 中提供 `case_id`。
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
