'use client'

import { useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import {
  BadgeCheck,
  Bookmark,
  ChevronRight,
  Clock,
  Loader2,
  MapPin,
  Briefcase,
  X,
} from 'lucide-react'

import { gatewayJson } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface RecommendationsPageProps {
  runtimeContext: HerRuntimeContext
  onViewCandidate: (candidateId: string) => void
}

type CardRow = {
  card_id: string
  subscription_id: string
  recommendation_id: string
  candidate_id: number
  card_status: 'unread' | 'read'
  title: string
  subtitle?: string
  body?: string
  delivered_at?: string
  payload?: {
    result_snapshot?: {
      id?: number
      name?: string
      score?: number
      photo_preview?: string[]
      profile?: {
        age?: number
        city?: string
        job?: string
        education?: string
      }
      verified_label?: string
      trust_summary?: {
        headline?: string
      }
    }
  }
}

type FilterType = 'all' | 'unread' | 'saved'

export default function RecommendationsPage({
  runtimeContext,
  onViewCandidate,
}: RecommendationsPageProps) {
  const [cards, setCards] = useState<CardRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterType>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const requesterId = runtimeContext.requesterId

  useEffect(() => {
    let active = true

    async function loadCards() {
      if (!requesterId) {
        setLoading(false)
        setError('缺少 requester_id，当前无法读取推荐卡片。')
        return
      }

      setLoading(true)
      setError(null)

      try {
        const payload = await gatewayJson<{ cards: CardRow[] }>(
          `/v1/recommendation/cards?requester_id=${requesterId}`,
        )
        if (!active) {
          return
        }
        setCards(payload.cards || [])
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '推荐卡片加载失败')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadCards()
    return () => {
      active = false
    }
  }, [requesterId])

  const filteredCards = useMemo(() => {
    return cards.filter((card) => {
      if (dismissedIds.has(card.card_id)) {
        return false
      }
      if (filter === 'unread') {
        return card.card_status === 'unread'
      }
      if (filter === 'saved') {
        return savedIds.has(card.card_id)
      }
      return true
    })
  }, [cards, dismissedIds, filter, savedIds])

  const unreadCount = cards.filter((card) => card.card_status === 'unread' && !dismissedIds.has(card.card_id)).length

  async function recordAction(card: CardRow, action: 'save' | 'skip') {
    try {
      await gatewayJson('/v1/recommendation/actions', {
        method: 'POST',
        body: JSON.stringify({
          subscription_id: card.subscription_id,
          candidate_id: card.candidate_id,
          action,
        }),
      })
    } catch {
      // UI optimistic only
    }
  }

  return (
    <div className="flex flex-col h-full">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="editorial-title text-2xl text-foreground">推荐</h1>
                <p className="text-xs text-muted-foreground mt-0.5">平台持续为你留意的人</p>
              </div>
              {unreadCount > 0 ? (
                <div className="px-3 py-1 bg-primary/10 rounded-full">
                  <span className="text-xs font-medium text-primary">{unreadCount} 条未读</span>
                </div>
              ) : null}
            </div>
          </div>
          <div className="px-5 pb-3 flex gap-2">
            {[
              { id: 'all' as const, label: '全部' },
              { id: 'unread' as const, label: '未读' },
              { id: 'saved' as const, label: '已收藏' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  filter === tab.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary/60 text-muted-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在读取推荐卡片
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : filteredCards.length === 0 ? (
          <div className="rounded-3xl border border-border/30 bg-card p-8 text-center text-sm text-muted-foreground shadow-soft">
            当前筛选下还没有可展示的推荐。
          </div>
        ) : (
          filteredCards.map((card) => {
            const snapshot = card.payload?.result_snapshot || {}
            const profile = snapshot.profile || {}
            const image = snapshot.photo_preview?.[0] || '/placeholder-user.jpg'
            const candidateId = snapshot.id || card.candidate_id
            return (
              <div
                key={card.card_id}
                onClick={() => onViewCandidate(String(candidateId))}
                className="cursor-pointer rounded-3xl overflow-hidden border border-border/50 bg-card shadow-soft transition-all active:scale-[0.99]"
                role="button"
                tabIndex={0}
              >
                <div className="flex gap-4 p-4">
                  <div className="relative h-36 w-28 shrink-0 overflow-hidden rounded-2xl bg-secondary">
                    <Image
                      src={image}
                      alt={snapshot.name || card.title}
                      fill
                      className="object-cover"
                      unoptimized={image.startsWith('http')}
                    />
                    {card.card_status === 'unread' ? (
                      <div className="absolute top-2 left-2 rounded-full bg-rose px-2 py-0.5 text-[10px] text-white">
                        新
                      </div>
                    ) : null}
                    {snapshot.score ? (
                      <div className="absolute bottom-2 left-2 rounded-full bg-gold/90 px-2 py-0.5 text-[10px] font-semibold text-foreground">
                        {snapshot.score}%
                      </div>
                    ) : null}
                  </div>

                  <div className="min-w-0 flex-1 py-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-foreground">
                        {snapshot.name || card.title.replace(/^发现新的合适对象：/, '')}
                      </h3>
                      {snapshot.verified_label ? (
                        <BadgeCheck className="h-4 w-4 text-primary shrink-0" />
                      ) : null}
                    </div>

                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      {profile.city ? (
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {profile.city}
                        </span>
                      ) : null}
                      {profile.job ? (
                        <span className="flex items-center gap-1">
                          <Briefcase className="h-3 w-3" />
                          {profile.job}
                        </span>
                      ) : null}
                      {profile.education ? <span>{profile.education}</span> : null}
                      {profile.age ? <span>{profile.age} 岁</span> : null}
                    </div>

                    <div className="mt-3 rounded-xl bg-blush/50 px-3 py-2">
                      <p className="text-xs leading-5 text-taupe whitespace-pre-wrap line-clamp-4">
                        {card.body || snapshot.trust_summary?.headline || '建议进入详情页继续确认。'}
                      </p>
                    </div>

                    <div className="mt-3 flex items-center justify-between">
                      <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {card.delivered_at || '刚刚送达'}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={async (event) => {
                            event.stopPropagation()
                            setDismissedIds((prev) => new Set(prev).add(card.card_id))
                            await recordAction(card, 'skip')
                          }}
                          className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary/60"
                        >
                          <X className="h-4 w-4 text-muted-foreground" />
                        </button>
                        <button
                          onClick={async (event) => {
                            event.stopPropagation()
                            setSavedIds((prev) => {
                              const next = new Set(prev)
                              if (next.has(card.card_id)) {
                                next.delete(card.card_id)
                              } else {
                                next.add(card.card_id)
                              }
                              return next
                            })
                            await recordAction(card, 'save')
                          }}
                          className={`flex h-8 w-8 items-center justify-center rounded-full ${
                            savedIds.has(card.card_id) ? 'bg-gold/20' : 'bg-secondary/60'
                          }`}
                        >
                          <Bookmark
                            className={`h-4 w-4 ${
                              savedIds.has(card.card_id) ? 'fill-gold text-gold' : 'text-muted-foreground'
                            }`}
                          />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="border-t border-border/30 px-4 py-2.5 text-center text-xs font-medium text-primary">
                  <span className="inline-flex items-center gap-1">
                    查看详细资料
                    <ChevronRight className="h-3.5 w-3.5" />
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
