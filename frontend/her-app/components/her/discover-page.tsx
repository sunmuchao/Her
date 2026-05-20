'use client'

import { useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { Loader2, Send, Sparkles, BadgeCheck, ChevronRight } from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface DiscoverPageProps {
  runtimeContext: HerRuntimeContext
  onViewCandidate: (candidateId: string) => void
  onSessionChange?: (sessionId?: string) => void
}

type DiscoveryCard = {
  card_id: string
  profile_id: number
  title: string
  subtitle?: string
  cover_image_url?: string | null
  match_score?: number | null
  trust_badges?: string[]
  reason_summary?: string
}

type DiscoveryTimelineItem =
  | { item_type: 'assistant_message' | 'user_message'; item_id: string; body: string }
  | { item_type: 'result_group'; item_id: string; title: string; cards: DiscoveryCard[] }

type DiscoveryResponse = {
  session: {
    session_id: string
    status: string
    phase: string
    updated_at: string
  }
  view: {
    timeline: DiscoveryTimelineItem[]
    criteria_chips: Array<{ chip_id: string; label: string }>
    suggested_actions: Array<{ action_id: string; label: string; style?: string }>
    composer?: { placeholder?: string; disabled?: boolean }
  }
  trace_id?: string
}

function isResultGroup(
  item: DiscoveryTimelineItem,
): item is Extract<DiscoveryTimelineItem, { item_type: 'result_group' }> {
  return item.item_type === 'result_group'
}

function sessionStorageKey(context: HerRuntimeContext) {
  return `her-discovery-session:${context.requesterId || 'unknown'}:${context.profileId || 'unknown'}`
}

export default function DiscoverPage({
  runtimeContext,
  onViewCandidate,
  onSessionChange,
}: DiscoverPageProps) {
  const [inputValue, setInputValue] = useState('')
  const [data, setData] = useState<DiscoveryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canStartSession = Boolean(runtimeContext.requesterId && runtimeContext.profileId)

  useEffect(() => {
    let active = true

    async function bootstrap() {
      if (!canStartSession) {
        setLoading(false)
        setError('缺少 requester_id 或 profile_id，当前无法创建发现会话。')
        return
      }

      setLoading(true)
      setError(null)

      try {
        const storedSessionId =
          typeof window !== 'undefined'
            ? window.sessionStorage.getItem(sessionStorageKey(runtimeContext))
            : null

        let next: DiscoveryResponse
        if (storedSessionId) {
          next = await gatewayJson<DiscoveryResponse>(`/v1/discovery/sessions/${storedSessionId}`)
        } else {
          next = await gatewayJson<DiscoveryResponse>('/v1/discovery/sessions', {
            method: 'POST',
            body: JSON.stringify({
              requester_id: runtimeContext.requesterId,
              profile_id: runtimeContext.profileId,
            }),
          })
          if (typeof window !== 'undefined') {
            window.sessionStorage.setItem(sessionStorageKey(runtimeContext), next.session.session_id)
          }
        }

        if (!active) {
          return
        }
        setData(next)
        onSessionChange?.(next.session.session_id)
      } catch (err) {
        if (!active) {
          return
        }
        const message = err instanceof Error ? err.message : '发现页初始化失败'
        setError(message)
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    bootstrap()
    return () => {
      active = false
    }
  }, [canStartSession, onSessionChange, runtimeContext])

  const suggestedActions = data?.view.suggested_actions || []
  const timeline = data?.view.timeline || []
  const criteriaChips = data?.view.criteria_chips || []
  const composer = data?.view.composer

  const latestResultCount = useMemo(() => {
    const group = [...timeline].reverse().find((item) => item.item_type === 'result_group') as
      | Extract<DiscoveryTimelineItem, { item_type: 'result_group' }>
      | undefined
    return group?.cards?.length || 0
  }, [timeline])

  async function submitTurn(payload: { user_message?: string; action_id?: string }) {
    if (!data?.session.session_id) {
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const next = await gatewayJson<DiscoveryResponse>(
        `/v1/discovery/sessions/${data.session.session_id}/turns`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      )
      setData(next)
      onSessionChange?.(next.session.session_id)
      setInputValue('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-background via-background to-blush/20">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="absolute inset-0 bg-background/80 backdrop-blur-xl" />
        <div className="relative px-5 py-4 border-b border-border/20">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#c8a888] via-[#d4b89a] to-[#b89878] p-[2px] shadow-lg">
              <div className="w-full h-full rounded-full bg-gradient-to-br from-gold-soft to-gold flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-foreground" strokeWidth={1.5} />
              </div>
            </div>
            <div className="min-w-0">
              <h1 className="font-semibold text-foreground text-lg">AI 红娘发现</h1>
              <p className="text-xs text-muted-foreground">
                {data?.session.phase
                  ? `当前阶段：${data.session.phase}`
                  : '通过对话逐步理解你的偏好'}
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="px-5 py-3 flex gap-2 overflow-x-auto scrollbar-hide">
        {criteriaChips.length === 0 ? (
          <span className="text-xs text-muted-foreground">红娘会在对话中逐步沉淀你的偏好</span>
        ) : (
          criteriaChips.map((chip) => (
            <span
              key={chip.chip_id}
              className="shrink-0 px-3 py-1.5 bg-gradient-to-r from-blush/80 to-rose-soft/60 text-taupe text-xs rounded-full border border-rose-soft/50 shadow-sm"
            >
              {chip.label}
            </span>
          ))
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {loading && (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            正在连接发现会话
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading &&
          timeline.map((item) => {
            if (item.item_type === 'assistant_message' || item.item_type === 'user_message') {
              const isUser = item.item_type === 'user_message'
              return (
                <div
                  key={item.item_id}
                  className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[82%] rounded-3xl px-4 py-3 shadow-sm ${
                      isUser
                        ? 'bg-gradient-to-br from-primary to-rose text-primary-foreground rounded-br-lg'
                        : 'bg-card/90 backdrop-blur-sm text-card-foreground border border-border/30 rounded-bl-lg'
                    }`}
                  >
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{item.body}</p>
                  </div>
                </div>
              )
            }

            if (!isResultGroup(item)) {
              return null
            }

            const resultGroup = item

            return (
              <section
                key={resultGroup.item_id}
                className="rounded-[28px] overflow-hidden bg-gradient-to-br from-card via-blush/15 to-rose-soft/20 border border-border/40 p-4 shadow-elevated"
              >
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">{resultGroup.title}</p>
                    <p className="text-xs text-muted-foreground">
                      这一轮为你筛出 {resultGroup.cards.length} 位可继续了解的人
                    </p>
                  </div>
                  <span className="rounded-full bg-gold-soft px-3 py-1 text-xs text-taupe">
                    {latestResultCount} 位候选人
                  </span>
                </div>

                <div className="space-y-3">
                  {resultGroup.cards.map((card: DiscoveryCard) => (
                    <button
                      key={card.card_id}
                      onClick={() => onViewCandidate(String(card.profile_id))}
                      className="w-full overflow-hidden rounded-2xl bg-background text-left shadow-soft border border-border/40"
                    >
                      <div className="flex gap-3 p-3">
                        <div className="relative h-28 w-24 shrink-0 overflow-hidden rounded-2xl bg-secondary">
                          {card.cover_image_url ? (
                            <Image
                              src={card.cover_image_url}
                              alt={card.title}
                              fill
                              className="object-cover"
                            />
                          ) : null}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start gap-2">
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-foreground">{card.title}</p>
                              <p className="mt-1 text-xs text-muted-foreground">{card.subtitle}</p>
                            </div>
                            {card.match_score ? (
                              <span className="rounded-full bg-gold-soft px-2 py-1 text-[11px] font-medium text-taupe">
                                {card.match_score}%
                              </span>
                            ) : null}
                          </div>

                          <div className="mt-3 flex flex-wrap gap-2">
                            {(card.trust_badges || []).slice(0, 2).map((badge: string) => (
                              <span
                                key={badge}
                                className="inline-flex items-center gap-1 rounded-full bg-rose-soft/50 px-2.5 py-1 text-[11px] text-taupe"
                              >
                                <BadgeCheck className="h-3 w-3 text-primary" />
                                {badge}
                              </span>
                            ))}
                          </div>

                          <p className="mt-3 text-xs leading-5 text-taupe line-clamp-2">
                            {card.reason_summary || '红娘建议先查看这位的详细资料。'}
                          </p>
                          <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary">
                            查看资料
                            <ChevronRight className="h-3.5 w-3.5" />
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            )
          })}
      </div>

      <div className="border-t border-border/30 bg-background/90 px-5 pb-6 pt-4 backdrop-blur-xl safe-area-bottom">
        {suggestedActions.length > 0 ? (
          <div className="mb-3 flex gap-2 overflow-x-auto scrollbar-hide">
            {suggestedActions.map((action) => (
              <button
                key={action.action_id}
                disabled={submitting}
                onClick={() => submitTurn({ action_id: action.action_id })}
                className={`shrink-0 rounded-full px-4 py-2 text-sm transition ${
                  action.style === 'primary'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground'
                }`}
              >
                {action.label}
              </button>
            ))}
          </div>
        ) : null}

        <div className="flex items-end gap-3">
          <div className="flex-1 rounded-3xl border border-border/40 bg-card px-4 py-3 shadow-soft">
            <textarea
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              rows={1}
              disabled={submitting || composer?.disabled}
              placeholder={composer?.placeholder || '告诉红娘你的偏好，她会替你整理并搜索。'}
              className="w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>
          <button
            disabled={submitting || !inputValue.trim() || composer?.disabled}
            onClick={() => submitTurn({ user_message: inputValue.trim() })}
            className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-r from-primary to-rose text-primary-foreground shadow-elevated disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
