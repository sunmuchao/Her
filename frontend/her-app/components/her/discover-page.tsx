'use client'

import { useState } from 'react'
import { ArrowLeft, BadgeCheck, Bookmark, ChevronRight, Mail, MapPin, Mic, Search, Send, X } from 'lucide-react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import Image from 'next/image'
import { EmptyRecommendations, EmptySearchResults } from './ui/empty-states'
import { InboxItemSkeleton, DiscoverPageSkeleton } from './ui/skeletons'
import { TypingIndicator } from './ui/typing-indicator'
import { OnlineIndicator } from './ui/animations'
import { DiscoveryCandidateCard } from './discovery-candidate-card'
import { DiscoveryProfileUpdatePrompt } from './discovery-profile-update-prompt'
import type { DiscoveryTimelineItem } from '@/lib/discovery/map-discovery-view'
import { cn } from '@/lib/utils'
import { getProfileId } from '@/lib/auth/session'
import {
  markRecommendationCardsRead,
  postRecommendationAction,
} from '@/lib/api/endpoints/recommendation'
import { replyProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { useRecommendationInbox, type InboxItem } from '@/hooks/use-recommendation-inbox'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { toast } from 'sonner'
import { EMPTY_PREFS_PLACEHOLDER } from '@/lib/fixtures/demo-profiles'
import type { CandidatePreview } from '@/lib/types/candidate'
import { useDiscoverySession } from '@/hooks/use-discovery-session'
import { useVoiceInput } from '@/hooks/use-voice-input'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onOpenInbox: () => void
  inboxUnreadCount?: number
  onSessionIdChange?: (sessionId: string | null) => void
}

function DiscoveryTimelineEntry({
  item,
  sessionId,
  onViewCandidate,
  onProfileUpdateResolved,
}: {
  item: DiscoveryTimelineItem
  sessionId: string | null
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onProfileUpdateResolved?: () => void
}) {
  if (item.kind === 'profile_update_prompt') {
    if (!sessionId) return null
    return (
      <DiscoveryProfileUpdatePrompt
        sessionId={sessionId}
        item={item}
        onResolved={() => onProfileUpdateResolved?.()}
      />
    )
  }

  if (item.kind === 'message') {
    const isUser = item.type === 'user'
    return (
      <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
        <div className={cn('max-w-[80%]', isUser ? 'order-1' : '')}>
          <div
            className={cn(
              'px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
              isUser
                ? 'bg-primary text-primary-foreground rounded-br-md'
                : 'bg-card border border-border rounded-bl-md',
            )}
          >
            {item.content}
          </div>
          <p className={cn('text-[10px] text-muted-foreground mt-1', isUser ? 'text-right' : '')}>
            {item.timestamp}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2 max-w-[92%]">
      {item.title ? <p className="text-xs text-muted-foreground">{item.title}</p> : null}
      <div className="space-y-3">
        {item.candidates.map((candidate, index) => (
          <DiscoveryCandidateCard
            key={`${item.id}-${candidate.id}`}
            candidate={candidate}
            onViewCandidate={onViewCandidate}
            className="animate-fade-in-up"
            style={{ animationDelay: `${index * 80}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

export default function DiscoverPage({
  onViewCandidate,
  onOpenInbox,
  inboxUnreadCount = 0,
  onSessionIdChange,
}: DiscoverPageProps) {
  const {
    timelineItems,
    inputValue,
    setInputValue,
    isTyping,
    currentPrefs,
    suggestedActions,
    composerPlaceholder,
    composerDisabled,
    isSubmittingTurn,
    loadError,
    usingMockData,
    isLoadingSession,
    chatEndRef,
    submitTurn,
    sessionId,
    reloadSession,
  } = useDiscoverySession(onSessionIdChange)

  // Voice input functionality
  const {
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    cancelRecording,
    recordingDuration,
  } = useVoiceInput({
    onTranscript: (text) => {
      setInputValue((prev) => prev + text)
    },
    onError: (error) => {
      toast.error(error)
    },
    maxDurationMs: 60000,
  })

  const handleVoiceClick = () => {
    if (isRecording) {
      stopRecording()
    } else {
      void startRecording()
    }
  }

  const formatRecordingTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const prefChips = currentPrefs.length
    ? currentPrefs
    : usingMockData
      ? ['同城优先', '本科以上']
      : []

  const pageShellClass =
    'flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background pb-14'

  if (isLoadingSession) {
    return (
      <div className={pageShellClass}>
        <DiscoverPageSkeleton />
      </div>
    )
  }

  if (loadError && !canUseMockFallback()) {
    return (
      <div className={pageShellClass}>
        <ErrorState
          message={loadError}
          onRetry={() => window.location.reload()}
        />
      </div>
    )
  }

  return (
    <div className={pageShellClass}>
      {usingMockData && <DemoDataBanner />}
      <header className="flex-shrink-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="relative">
                <XiaoyaAvatar size={40} />
                <OnlineIndicator className="absolute -bottom-0.5 -right-0.5" size="sm" />
              </div>
              <div>
                <h1 className="font-medium text-foreground">小雅</h1>
                <p className="text-xs text-muted-foreground">你的专属红娘</p>
              </div>
            </div>
            <button 
              onClick={onOpenInbox} 
              className="relative flex items-center gap-2 px-3 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors focus-ring"
              aria-label={`查看推荐来信，${inboxUnreadCount}条未读`}
            >
              <Mail className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
              <span className="text-sm">来信</span>
              {inboxUnreadCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center animate-scale-in">
                  {inboxUnreadCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Preference chips with scroll fade */}
      <div className="relative flex-shrink-0 px-4 py-2 border-b border-border">
        <p className="text-[10px] text-muted-foreground mb-1.5">当前条件</p>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide scroll-fade-right" role="list" aria-label="已收集偏好">
          {currentPrefs.length === 0 && !usingMockData ? (
            <span className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md">
              {EMPTY_PREFS_PLACEHOLDER}
            </span>
          ) : (
            prefChips.map((pref, i) => (
            <span 
              key={i} 
              className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md animate-fade-in-up"
              style={{ animationDelay: `${i * 50}ms` }}
              role="listitem"
            >
              {pref}
            </span>
          )))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
        <div className="px-4 py-4 space-y-4">
          {timelineItems.map((item) => (
            <DiscoveryTimelineEntry
              key={item.id}
              item={item}
              sessionId={sessionId}
              onViewCandidate={onViewCandidate}
              onProfileUpdateResolved={() => {
                void reloadSession()
              }}
            />
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

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Input pinned below scrollable messages; app shell bottom nav is outside this column */}
      <div className="flex-shrink-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        {/* Recording indicator */}
        {isRecording && (
          <div className="flex items-center justify-between mb-2 px-3 py-2 bg-rose/10 rounded-lg animate-fade-in-up">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-rose rounded-full animate-pulse" />
              <span className="text-sm text-rose font-medium">正在录音</span>
              <span className="text-sm text-muted-foreground">{formatRecordingTime(recordingDuration)}</span>
            </div>
            <button
              onClick={cancelRecording}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              aria-label="取消录音"
            >
              取消
            </button>
          </div>
        )}
        
        {isProcessing && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-secondary rounded-lg animate-fade-in-up">
            <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm text-muted-foreground">识别中...</span>
          </div>
        )}

        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2 transition-all focus-within:ring-2 focus-within:ring-primary/30">
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && inputValue.trim()) {
                e.preventDefault()
                void submitTurn({ user_message: inputValue.trim() })
              }
            }}
            placeholder={isRecording ? '请说话...' : composerPlaceholder}
            disabled={composerDisabled || isSubmittingTurn || isRecording}
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-60"
            aria-label="输入消息"
          />
          
          {/* Voice input button */}
          <button
            aria-label={isRecording ? '停止录音' : '语音输入'}
            onClick={handleVoiceClick}
            disabled={composerDisabled || isSubmittingTurn || isProcessing}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              isRecording
                ? 'bg-rose text-white animate-pulse'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80'
            )}
          >
            <Mic className="w-5 h-5" />
          </button>
          
          <button
            aria-label="发送消息"
            onClick={() => void submitTurn({ user_message: inputValue.trim() })}
            disabled={composerDisabled || isSubmittingTurn || !inputValue.trim() || isRecording}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              inputValue.trim() && !isRecording
                ? 'bg-primary hover:bg-primary/90' 
                : 'bg-muted'
            )}
          >
            {isSubmittingTurn ? (
              <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            ) : (
              <Send className={cn('w-4 h-4', inputValue.trim() && !isRecording ? 'text-primary-foreground' : 'text-muted-foreground')} />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export function RecommendationInbox({
  onViewCandidate,
  onBack,
  onBadgesRefresh,
}: {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onBack: () => void
  onBadgesRefresh?: () => void
}) {
  const [filter, setFilter] = useState<'all' | 'delayed' | 'matched' | 'interest'>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)  // 正在处理的 case
  const { isLoading, backendItems } = useRecommendationInbox()

  const filteredItems = backendItems.filter((item) => {
    if (dismissedIds.has(item.listKey)) return false
    if (filter === 'delayed') return item.type === 'delayed'
    if (filter === 'matched') return item.type === 'matched'
    if (filter === 'interest') return item.type === 'interest'  // 新增：有人想认识你
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return item.name.toLowerCase().includes(q) || item.city.toLowerCase().includes(q) || item.occupation.toLowerCase().includes(q)
    }
    return true
  })

  // 处理被动推荐卡片的回复
  const handleInterestReply = async (caseId: string, replyType: 'accepted' | 'declined') => {
    if (actingCaseId) return  // 防止重复点击
    setActingCaseId(caseId)
    try {
      await replyProxyIntroCase({
        caseId,
        replyType,
        source: 'recommendation_inbox',
      })
      if (replyType === 'declined') {
        setDismissedIds((prev) => new Set(prev).add(`case:${caseId}`))
      }
      toast.success(replyType === 'accepted' ? '已表达意愿，可以开始聊天了' : '已暂不考虑')
    } catch (error) {
      notifyError(error, replyType === 'accepted' ? '接受失败' : '暂不考虑失败')
    } finally {
      setActingCaseId(null)
    }
  }

  const markRead = async (item: InboxItem) => {
    const profileId = getProfileId()
    if (!profileId || !item.cardId) return
    try {
    await markRecommendationCardsRead(Number(profileId), [item.cardId])
      onBadgesRefresh?.()
    } catch (error) {
      notifyError(error, '标记已读失败')
    }
  }

  const recordAction = async (item: InboxItem, actionType: string) => {
    if (!item.subscriptionId || !item.candidateId) return
    const idem = `${item.subscriptionId}:${item.candidateId}:${actionType}`
    try {
    await postRecommendationAction({
      subscriptionId: item.subscriptionId,
      candidateId: item.candidateId,
      actionType,
      idempotencyKey: idem,
    })
    } catch (error) {
      notifyError(error, '操作失败，请重试')
    }
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
            { id: 'interest' as const, label: '有人想认识你' },  // 新增
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
              key={item.listKey}
              onClick={() => {
                // 被动推荐卡片（有人想认识你）不跳转到详情页，直接显示操作按钮
                if (item.type !== 'interest') {
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
                    recommendationId: item.recommendationId,
                    subscriptionId: item.subscriptionId,
                  })
                }
              }}
              className={`bg-card border border-border rounded-xl p-3 transition-colors ${item.type !== 'interest' ? 'cursor-pointer hover:border-primary/30' : ''}`}
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
                  <span className={`px-2 py-0.5 rounded text-[10px] ${
                    item.type === 'delayed' ? 'bg-gold/20 text-gold' :
                    item.type === 'interest' ? 'bg-primary/20 text-primary' :
                    'bg-rose/20 text-rose'
                  }`}>
                    {item.conversionStage || (
                      item.type === 'delayed' ? '延迟推荐' :
                      item.type === 'interest' ? '有人想认识你' :
                      '主动撮合'
                    )}
                  </span>
                </div>
                {/* 被动推荐卡片显示操作按钮 */}
                {item.type === 'interest' && item.caseId ? (
                  <div className="flex gap-2">
                    <button
                      aria-label={`暂不考虑${item.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleInterestReply(item.caseId!, 'declined')
                      }}
                      disabled={actingCaseId === item.caseId}
                      className="px-3 py-1 rounded-lg border border-border text-xs disabled:opacity-50"
                    >
                      {actingCaseId === item.caseId ? '处理中' : '暂不考虑'}
                    </button>
                    <button
                      aria-label={`愿意认识${item.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleInterestReply(item.caseId!, 'accepted')
                      }}
                      disabled={actingCaseId === item.caseId}
                      className="px-3 py-1 rounded-lg bg-primary text-xs text-primary-foreground disabled:opacity-50"
                    >
                      {actingCaseId === item.caseId ? '处理中' : '愿意认识'}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1">
                    <button
                      aria-label={`跳过${item.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void recordAction(item, 'skip')
                        setDismissedIds((prev) => new Set(prev).add(item.listKey))
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
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
