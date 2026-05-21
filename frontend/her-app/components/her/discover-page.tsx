'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, BadgeCheck, Bookmark, ChevronRight, Mail, MapPin, Search, Send, X } from 'lucide-react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import Image from 'next/image'
import { EmptyRecommendations, EmptySearchResults } from './ui/empty-states'
import { InboxItemSkeleton } from './ui/skeletons'
import { TypingIndicator } from './ui/typing-indicator'
import { gatewayJson, queryString } from '@/lib/gateway'
import type { CandidatePreview } from '@/lib/her-types'

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onOpenInbox: () => void
  inboxUnreadCount?: number
}

type DiscoveryView = {
  timeline?: Array<{
    item_type?: string
    item_id?: string
    body?: string
    cards?: Array<{
      card_id?: string
      profile_id?: string | number
      title?: string
      subtitle?: string
      cover_image_url?: string
      match_score?: number
      reason_summary?: string
    }>
  }>
  criteria_chips?: Array<{ label?: string }>
  suggested_actions?: Array<{ action_id?: string; label?: string }>
  composer?: { placeholder?: string; disabled?: boolean }
}

type DiscoverySessionResponse = {
  session?: { session_id?: string }
  view?: DiscoveryView
}

type RecommendationCardsResponse = {
  cards?: Array<{
    card_id: string
    subscription_id?: string
    recommendation_id?: number
    candidate_id?: number
    card_status?: string
    title?: string
    body?: string
    created_at?: string
    payload?: {
      cta_actions?: Array<{ id?: string; label?: string }>
      result_snapshot?: {
        id?: number
        name?: string
        score?: number
        profile?: {
          age?: number
          city?: string
          job?: string
          avatar_url?: string
        }
      }
    }
  }>
}

type InboxItem = {
  id: string
  cardId?: string
  subscriptionId?: string
  recommendationId?: number
  candidateId?: number
  name: string
  age: number
  city: string
  occupation: string
  matchScore: number
  image: string
  type: 'delayed' | 'matched'
  message: string
  time: string
  isRead: boolean
}

const initialMessages = [
  { id: '1', type: 'matchmaker' as const, content: '你好，我是你的专属红娘小雅。接下来我会帮你找到那个对的人。', timestamp: '09:30' },
  { id: '2', type: 'matchmaker' as const, content: '你理想中的伴侣是什么样的？', timestamp: '09:31' },
]

const fallbackCandidates: CandidatePreview[] = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    verified: true,
    matchScore: 95,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=600&fit=crop&crop=face',
    matchReason: '性格温和、同城、审美品味相近',
  },
  {
    id: '2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    education: '浙江大学',
    verified: true,
    matchScore: 92,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=400&h=600&fit=crop&crop=face',
    matchReason: '价值观相似、兴趣爱好匹配',
  },
]

const fallbackInboxItems: InboxItem[] = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    matchScore: 95,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
    type: 'delayed',
    message: '她符合你的期待，性格温和，同在上海',
    time: '2小时前',
    isRead: false,
  },
]

const fallbackPrefs = ['同城优先', '本科以上', '年龄相近', '性格温柔']

function mapDiscoveryView(view?: DiscoveryView) {
  const messages =
    view?.timeline
      ?.filter((item) => item.item_type === 'assistant_message' || item.item_type === 'user_message')
      .map((item, index) => ({
        id: item.item_id || String(index),
        type: item.item_type === 'user_message' ? ('user' as const) : ('matchmaker' as const),
        content: item.body || '',
        timestamp: '刚刚',
      })) || []

  const chips = view?.criteria_chips?.map((item) => item.label).filter(Boolean) as string[] | undefined
  const actions =
    view?.suggested_actions
      ?.filter((item): item is { action_id: string; label: string } => Boolean(item.action_id && item.label))
      .map((item) => ({ action_id: item.action_id, label: item.label })) || []
  const candidates =
    view?.timeline
      ?.flatMap((item) => (item.item_type === 'result_group' ? item.cards || [] : []))
      .map((card) => ({
        id: String(card.profile_id || card.card_id || ''),
        name: card.title || '候选人',
        city: card.subtitle || undefined,
        image: card.cover_image_url,
        matchScore: card.match_score,
        matchReason: card.reason_summary,
      }))
      .filter((item) => item.id) || []

  return {
    messages,
    chips,
    actions,
    candidates,
    composerPlaceholder: view?.composer?.placeholder || '输入你的想法...',
    composerDisabled: Boolean(view?.composer?.disabled),
  }
}

export default function DiscoverPage({ onViewCandidate, onOpenInbox, inboxUnreadCount = 3 }: DiscoverPageProps) {
  const [messages, setMessages] = useState(initialMessages)
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [currentPrefs, setCurrentPrefs] = useState(fallbackPrefs)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [suggestedActions, setSuggestedActions] = useState<Array<{ action_id: string; label: string }>>([])
  const [composerPlaceholder, setComposerPlaceholder] = useState('输入你的想法...')
  const [composerDisabled, setComposerDisabled] = useState(false)
  const [isSubmittingTurn, setIsSubmittingTurn] = useState(false)
  const [backendCandidates, setBackendCandidates] = useState<CandidatePreview[]>([])
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsTyping(true)
      setTimeout(() => setIsTyping(false), 2500)
    }, 1500)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isTyping, suggestedActions, backendCandidates])

  useEffect(() => {
    const requesterId = process.env.NEXT_PUBLIC_HER_REQUESTER_ID
    const profileId = process.env.NEXT_PUBLIC_HER_PROFILE_ID
    if (!requesterId || !profileId) return
    let cancelled = false

    async function loadSession() {
      try {
        const data = await gatewayJson<DiscoverySessionResponse>('/v1/discovery/sessions', {
          method: 'POST',
          body: JSON.stringify({
            requester_id: Number(requesterId),
            profile_id: Number(profileId),
          }),
        })
        if (cancelled) return
        setSessionId(data.session?.session_id || null)
        const mapped = mapDiscoveryView(data.view)
        if (mapped.messages.length) setMessages(mapped.messages)
        if (mapped.chips?.length) setCurrentPrefs(mapped.chips)
        setSuggestedActions(mapped.actions)
        setComposerPlaceholder(mapped.composerPlaceholder)
        setComposerDisabled(mapped.composerDisabled)
        if (mapped.candidates.length) setBackendCandidates(mapped.candidates)
      } catch {
        // Keep design fallback when backend session is unavailable.
      }
    }

    void loadSession()
    return () => {
      cancelled = true
    }
  }, [])

  const submitTurn = async (payload: { user_message?: string; action_id?: string }) => {
    if (!sessionId) return
    setIsSubmittingTurn(true)
    try {
      const data = await gatewayJson<DiscoverySessionResponse>(`/v1/discovery/sessions/${sessionId}/turns`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      const mapped = mapDiscoveryView(data.view)
      if (mapped.messages.length) setMessages(mapped.messages)
      if (mapped.chips) setCurrentPrefs(mapped.chips.length ? mapped.chips : fallbackPrefs)
      setSuggestedActions(mapped.actions)
      setComposerPlaceholder(mapped.composerPlaceholder)
      setComposerDisabled(mapped.composerDisabled)
      if (mapped.candidates.length) setBackendCandidates(mapped.candidates)
      if (payload.user_message) setInputValue('')
    } finally {
      setIsSubmittingTurn(false)
    }
  }

  const visibleCandidates = backendCandidates.length ? backendCandidates : fallbackCandidates

  return (
    <div className="flex flex-col h-full bg-background">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <XiaoyaAvatar size={40} />
              <div>
                <h1 className="font-medium text-foreground">小雅</h1>
                <p className="text-xs text-muted-foreground">你的专属红娘</p>
              </div>
            </div>
            <button onClick={onOpenInbox} className="relative flex items-center gap-2 px-3 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors">
              <Mail className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">来信</span>
              {inboxUnreadCount > 0 ? (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center">
                  {inboxUnreadCount}
                </span>
              ) : null}
            </button>
          </div>
        </div>
      </header>

      <div className="px-4 py-2 flex gap-2 overflow-x-auto border-b border-border">
        {currentPrefs.map((pref, i) => (
          <span key={i} className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md">
            {pref}
          </span>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-4 py-4 space-y-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] ${msg.type === 'user' ? 'order-1' : ''}`}>
                <div className={`px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${msg.type === 'user' ? 'bg-primary text-primary-foreground rounded-br-md' : 'bg-card border border-border rounded-bl-md'}`}>
                  {msg.content}
                </div>
                <p className={`text-[10px] text-muted-foreground mt-1 ${msg.type === 'user' ? 'text-right' : ''}`}>{msg.timestamp}</p>
              </div>
            </div>
          ))}

          {isTyping ? <TypingIndicator name="小雅" /> : null}

          {suggestedActions.length ? (
            <div className="flex flex-wrap gap-2">
              {suggestedActions.map((action) => (
                <button
                  key={action.action_id}
                  onClick={() => void submitTurn({ action_id: action.action_id })}
                  disabled={isSubmittingTurn}
                  className="rounded-full border border-border bg-secondary px-3 py-1.5 text-xs text-foreground disabled:opacity-60"
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}

          {visibleCandidates.length ? (
            <div className="pt-4">
              <p className="text-xs text-muted-foreground mb-3">为你精心挑选</p>
              <div className="space-y-3">
                {visibleCandidates.map((candidate, index) => (
                  <button
                    key={candidate.id}
                    onClick={() => onViewCandidate(candidate.id, candidate)}
                    className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex gap-3">
                      <div className="relative w-16 h-20 rounded-lg overflow-hidden shrink-0 bg-secondary">
                        {candidate.image ? <Image src={candidate.image} alt={candidate.name} fill className="object-cover" /> : null}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">{candidate.name}</span>
                          {candidate.age ? <span className="text-sm text-muted-foreground">{candidate.age}岁</span> : null}
                          {candidate.verified ? <BadgeCheck className="w-4 h-4 text-primary" /> : null}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                          {candidate.city ? <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{candidate.city}</span> : null}
                          {candidate.occupation ? <span>{candidate.occupation}</span> : null}
                        </div>
                        {candidate.matchReason ? <p className="text-xs text-primary mt-2">{candidate.matchReason}</p> : null}
                      </div>
                      <div className="flex flex-col items-end justify-between">
                        {candidate.matchScore ? <span className="text-sm font-medium text-primary">{candidate.matchScore}%</span> : <span />}
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div ref={chatEndRef} />
        </div>
      </div>

      <div className="sticky bottom-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={composerPlaceholder}
            disabled={composerDisabled || isSubmittingTurn}
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
          <button
            aria-label="发送发现页消息"
            onClick={() => void submitTurn({ user_message: inputValue.trim() })}
            disabled={composerDisabled || isSubmittingTurn || !inputValue.trim()}
            className="w-8 h-8 rounded-full bg-primary flex items-center justify-center disabled:opacity-60"
          >
            <Send className="w-4 h-4 text-primary-foreground" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function RecommendationInbox({
  onViewCandidate,
  onBack,
}: {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onBack: () => void
}) {
  const [filter, setFilter] = useState<'all' | 'delayed' | 'matched'>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [backendItems, setBackendItems] = useState<InboxItem[]>(fallbackInboxItems)

  useEffect(() => {
    const requesterId = process.env.NEXT_PUBLIC_HER_REQUESTER_ID
    if (!requesterId) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    async function loadCards() {
      try {
        const response = await gatewayJson<RecommendationCardsResponse>(
          `/v1/recommendation/cards${queryString({ requester_id: Number(requesterId) })}`,
        )
        if (cancelled) return
        const cards =
          response.cards?.map((card) => {
            const snapshot = card.payload?.result_snapshot
            const profile = snapshot?.profile
            return {
              id: String(snapshot?.id || card.candidate_id || card.card_id),
              cardId: card.card_id,
              subscriptionId: card.subscription_id,
              recommendationId: card.recommendation_id,
              candidateId: snapshot?.id || card.candidate_id,
              name: snapshot?.name || card.title?.replace(/^发现新的合适对象：/, '') || '候选人',
              age: profile?.age || 0,
              city: profile?.city || '未知',
              occupation: profile?.job || '资料待补充',
              matchScore: snapshot?.score || 0,
              image: profile?.avatar_url || 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
              type: 'matched' as const,
              message: card.body || card.title || '系统为你推送了一位新候选人',
              time: card.created_at || '刚刚',
              isRead: card.card_status === 'read',
            }
          }) || []
        if (cards.length) {
          setBackendItems(cards)
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadCards()
    return () => {
      cancelled = true
    }
  }, [])

  const filteredItems = backendItems.filter((item) => {
    if (dismissedIds.has(item.id)) return false
    if (filter === 'delayed') return item.type === 'delayed'
    if (filter === 'matched') return item.type === 'matched'
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return item.name.toLowerCase().includes(q) || item.city.toLowerCase().includes(q) || item.occupation.toLowerCase().includes(q)
    }
    return true
  })

  const markRead = async (item: InboxItem) => {
    const requesterId = process.env.NEXT_PUBLIC_HER_REQUESTER_ID
    if (!requesterId || !item.cardId) return
    await gatewayJson('/v1/recommendation/cards/read', {
      method: 'POST',
      body: JSON.stringify({
        requester_id: Number(requesterId),
        card_ids: [item.cardId],
      }),
    })
  }

  const recordAction = async (item: InboxItem, actionType: string) => {
    if (!item.subscriptionId || !item.candidateId) return
    const idem = `${item.subscriptionId}:${item.candidateId}:${actionType}`
    await gatewayJson('/v1/recommendation/actions', {
      method: 'POST',
      headers: { 'Idempotency-Key': idem },
      body: JSON.stringify({
        subscription_id: item.subscriptionId,
        candidate_id: item.candidateId,
        action_type: actionType,
        client_idempotency_key: idem,
      }),
    })
  }

  return (
    <div className="flex flex-col h-full bg-background">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="font-medium">推荐来信</h1>
          </div>
        </div>

        <div className="px-4 pb-3 flex gap-2">
          {[
            { id: 'all' as const, label: '全部' },
            { id: 'delayed' as const, label: '延迟推荐' },
            { id: 'matched' as const, label: '主动撮合' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${filter === tab.id ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索姓名、城市、职业..."
              className="w-full pl-9 pr-8 py-2 bg-secondary rounded-lg text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {searchQuery ? (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {isLoading ? (
          <>
            <InboxItemSkeleton />
            <InboxItemSkeleton />
            <InboxItemSkeleton />
          </>
        ) : filteredItems.length === 0 ? (
          searchQuery ? <EmptySearchResults keyword={searchQuery} /> : <EmptyRecommendations onRefresh={onBack} />
        ) : (
          filteredItems.map((item) => (
            <div
              key={item.id}
              onClick={() => {
                void markRead(item)
                onViewCandidate(item.id, {
                  id: item.id,
                  name: item.name,
                  age: item.age,
                  city: item.city,
                  occupation: item.occupation,
                  verified: true,
                  matchScore: item.matchScore,
                  image: item.image,
                  message: item.message,
                })
              }}
              className="bg-card border border-border rounded-xl p-3 cursor-pointer hover:border-primary/30 transition-colors"
            >
              <div className="flex gap-3">
                <div className="relative w-14 h-14 rounded-lg overflow-hidden shrink-0">
                  <Image src={item.image} alt={item.name} fill className="object-cover" />
                  {!item.isRead ? <div className="absolute top-1 right-1 w-2 h-2 bg-rose rounded-full" /> : null}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      <span className="text-xs text-muted-foreground">{item.age}岁 · {item.city}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{item.time}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.occupation}</p>
                  <p className="text-sm text-foreground mt-1.5 line-clamp-1">{item.message}</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-border">
                <div className="flex items-center gap-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${item.type === 'delayed' ? 'bg-gold/20 text-gold' : 'bg-rose/20 text-rose'}`}>
                    {item.type === 'delayed' ? '延迟推荐' : '主动撮合'}
                  </span>
                  <span className="text-xs text-primary font-medium">{item.matchScore}% 匹配</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    aria-label={`跳过${item.name}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      void recordAction(item, 'skip')
                      setDismissedIds((prev) => new Set(prev).add(item.id))
                    }}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                  <button
                    aria-label={`收藏${item.name}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      void recordAction(item, 'save')
                      setSavedIds((prev) => {
                        const next = new Set(prev)
                        if (next.has(item.id)) next.delete(item.id)
                        else next.add(item.id)
                        return next
                      })
                    }}
                    className={`p-1.5 transition-colors ${savedIds.has(item.id) ? 'text-gold' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    <Bookmark className={`w-4 h-4 ${savedIds.has(item.id) ? 'fill-current' : ''}`} />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
